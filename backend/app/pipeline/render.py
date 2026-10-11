"""Fotorealismus-Stufe: pluggable Interface auf fixierter Geometrie.

WICHTIG (docs/LLM-DECISION.md, docs/ARCHITECTURE.md): Diese Stufe darf NIE
Wand-/Tuer-/Fensterpositionen veraendern - sie veredelt nur Material/Licht/Stil
auf dem bereits exakten GLB aus geometry.py. Produktionsreife Implementierungen
(SDXL+ControlNet via Replicate/Stability, oder Blender headless) werden hier
eingehaengt, siehe PhotorealRenderer-Protokoll.
"""
from __future__ import annotations

import io
from typing import Protocol

import trimesh
from PIL import Image

from app.core.config import get_settings


def _apply_camera_pose(scene: trimesh.Scene, camera_pose: dict | None) -> None:
    """Setzt die Kamera auf der (kopierten) Szene.

    Bevorzugt eine explizite 4x4-Transform (siehe
    geometry.py::interior_camera_transform - Innenraumperspektive statt
    Aussenansicht). Ohne Transform faellt dies auf die alte
    Aussenansicht-Orbit-Kamera zurueck (z.B. fuer Debug-/Uebersichtsbilder).
    """
    if not camera_pose:
        return
    transform = camera_pose.get("transform")
    if transform is not None:
        scene.camera_transform = transform
        # Realistisches Weitwinkel-Objektiv (ca. 24mm Kleinbild-Aequivalent)
        # statt extremem 80 Grad-FOV - vorher fuehrte der sehr weite Winkel
        # zu uebertriebener, "schwankender" Fluchtlinien-Verzerrung am Boden
        # (siehe docs/ARCHITECTURE.md Live-Testergebnis: Nutzer-Feedback
        # "Rendering sieht aus wie ein Schrank").
        scene.camera.fov = (68, 52)
        return
    scene.set_camera(
        angles=camera_pose.get("angles", (1.2, 0, 0)),
        distance=camera_pose.get("distance", 10.0),
        center=camera_pose.get("center", scene.centroid),
    )


class PhotorealRenderer(Protocol):
    """Erweiterungspunkt fuer produktionsreife Renderer.

    Eine echte Implementierung wuerde z.B.:
    1. Aus dem Scene-Objekt eine Depth-/Canny-Map pro Kameraposition rendern.
    2. Diese als ControlNet-Konditionierung an SDXL/FLUX (Replicate/Stability API)
       oder an Blender (Cycles, headless via bpy) uebergeben, mit der
       Stil-/Materialbeschreibung aus dem LLM-Schritt (docs/LLM-DECISION.md Punkt 4).
    3. Ein PNG zurueckgeben, dessen Silhouette exakt der Konditionierung entspricht.
    """

    def render(self, scene: trimesh.Scene, camera_pose: dict, style_prompt: str) -> bytes: ...


class SimplePreviewRenderer:
    """GPU-freier Fallback: schattierte Vorschau statt Fotorealismus.

    Zeigt die exakte Geometrie korrekt, aber bewusst NICHT fotorealistisch -
    ehrlicher Platzhalter, bis ein echter Renderer (siehe PhotorealRenderer)
    angebunden ist.
    """

    def render(self, scene: trimesh.Scene, camera_pose: dict | None = None, style_prompt: str = "") -> bytes:
        del style_prompt  # Preview-Renderer ignoriert Stilvorgaben bewusst
        scene_copy = scene.copy()
        _apply_camera_pose(scene_copy, camera_pose)
        png_bytes = scene_copy.save_image(resolution=(1024, 768), visible=True)
        if png_bytes is None:
            # Kein Display/Offscreen-Renderer verfuegbar (z.B. headless ohne
            # pyglet-Backend) - Platzhalterbild statt Fehlschlag zurueckgeben.
            placeholder = Image.new("RGB", (1024, 768), color=(235, 235, 230))
            buf = io.BytesIO()
            placeholder.save(buf, format="PNG")
            return buf.getvalue()
        return png_bytes


_NANO_BANANA_INSTRUCTION = (
    "Turn this simple 3D model render of an apartment room into a photorealistic "
    "real estate interior photograph. Keep the exact camera position and angle, and "
    "keep every wall, corner, window, door and opening exactly where it is with the "
    "same size and proportions - do not add, remove or move any walls, windows or "
    "doors. Replace the plain colored blocks with realistic furniture of the same "
    "size and position, give walls, floor and ceiling realistic materials and add "
    "natural lighting. Style: "
)


def _build_image_model_input(model_slug: str, render_png: bytes, render_file: io.BytesIO,
                             style_prompt: str) -> dict:
    """Eingabeschema je Bildmodell auf Replicate (Feldnamen und Arbeitsweise
    unterscheiden sich): FLUX Depth/Canny konditionieren auf ein Steuerbild,
    nano-banana (Gemini 2.5 Flash Image) ist ein Bild-BEARBEITUNGSmodell und
    bekommt das geometrisch exakte Innenraum-Rendering plus Anweisung, die
    Geometrie unveraendert zu lassen."""
    if model_slug.startswith("google/nano-banana"):
        import base64

        data_uri = "data:image/png;base64," + base64.standard_b64encode(render_png).decode()
        return {
            "prompt": _NANO_BANANA_INSTRUCTION + style_prompt,
            "image_input": [data_uri],
            "aspect_ratio": "match_input_image",
            "output_format": "png",
        }
    return {
        "control_image": render_file,
        "prompt": style_prompt,
        "guidance": 10,
        "num_inference_steps": 28,
    }


class ReplicateDepthRenderer:
    """Produktionsreifer Fotorealismus-Renderer via Replicate.

    Modellwahl (docs/LLM-DECISION.md): black-forest-labs/flux-depth-dev.
    FLUX.1 Depth [dev] nimmt eine Depth-Map + Text-Prompt und erzeugt ein
    fotorealistisches Bild, dessen Geometrie an die Depth-Map gebunden ist -
    genau das Prinzip aus docs/ARCHITECTURE.md ("Geometrie fixiert, nur
    Material/Licht/Stil wird generiert"). Die Depth-Map wird hier direkt aus
    dem exakten GLB gerendert (trimesh Offscreen-Depth-Buffer), nicht aus
    einem zweiten, unabhaengigen Modell.
    """

    def __init__(self, api_token: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        import replicate as replicate_sdk

        from app.pipeline.parser import _resolve_version_ref

        self._client = replicate_sdk.Client(api_token=api_token or settings.replicate_api_token)
        self._model_slug = model or settings.replicate_image_model
        self._model = _resolve_version_ref(self._client, self._model_slug)

    def _render_depth_map(self, scene: trimesh.Scene, camera_pose: dict | None) -> bytes:
        scene_copy = scene.copy()
        _apply_camera_pose(scene_copy, camera_pose)
        depth = scene_copy.save_image(resolution=(1024, 768), visible=True)
        if depth is None:
            raise RuntimeError(
                "Kein Offscreen-Renderer verfuegbar, um die Depth-Map fuer "
                "FLUX Depth zu erzeugen (benoetigt OpenGL-Kontext)."
            )
        return depth

    def render(self, scene: trimesh.Scene, camera_pose: dict, style_prompt: str) -> bytes:
        import replicate as replicate_sdk

        depth_png = self._render_depth_map(scene, camera_pose)
        depth_file = io.BytesIO(depth_png)

        # Live-Test (2026-10-11): "architectural magazine quality" im Prompt
        # fuehrte zuverlaessig zu halluzinierten Pseudo-Text-/Logo-Artefakten
        # (FLUX assoziiert "magazine" mit Cover-Typografie/Schlagzeilen aus
        # den Trainingsdaten). Ein nachtraeglich ergaenztes "no text, no
        # watermark, no logo" im Hauptprompt hat das NICHT behoben, sondern
        # tendenziell verschlimmert - FLUX.1 Depth [dev] hat kein echtes
        # negative_prompt-Feld, daher wirkt eine Verneinung im Positiv-Prompt
        # nicht als Ausschluss, sondern aktiviert eher die genannten Begriffe
        # (bekanntes Diffusionsmodell-Verhalten). Fix: "magazine" entfernt,
        # keine Verneinungen mehr im Prompt - nur noch neutrale
        # Fotografie-Begriffe ohne Editorial-/Typografie-Assoziation.
        base_prompt = style_prompt or (
            "professional real estate interior photography, realistic "
            "furniture and materials, natural daylight, sharp focus, "
            "DSLR photograph, 24mm wide-angle lens"
        )
        output = self._client.run(
            self._model, input=_build_image_model_input(self._model_slug, depth_png, depth_file, base_prompt)
        )
        result = output[0] if isinstance(output, list) else output
        if hasattr(result, "read"):
            return result.read()
        # Replicate kann auch eine URL zurueckgeben statt eines Streams.
        import httpx

        return httpx.get(str(result)).content


def get_renderer() -> PhotorealRenderer:
    """Factory: waehlt die Render-Implementierung nach settings.render_provider."""
    settings = get_settings()
    if settings.render_provider == "replicate":
        return ReplicateDepthRenderer()
    return SimplePreviewRenderer()


def get_default_renderer() -> PhotorealRenderer:
    return get_renderer()
