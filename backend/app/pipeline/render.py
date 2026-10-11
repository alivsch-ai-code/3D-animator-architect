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
        if camera_pose:
            scene_copy.set_camera(
                angles=camera_pose.get("angles", (1.2, 0, 0)),
                distance=camera_pose.get("distance", 10.0),
                center=camera_pose.get("center", scene_copy.centroid),
            )
        png_bytes = scene_copy.save_image(resolution=(1024, 768), visible=True)
        if png_bytes is None:
            # Kein Display/Offscreen-Renderer verfuegbar (z.B. headless ohne
            # pyglet-Backend) - Platzhalterbild statt Fehlschlag zurueckgeben.
            placeholder = Image.new("RGB", (1024, 768), color=(235, 235, 230))
            buf = io.BytesIO()
            placeholder.save(buf, format="PNG")
            return buf.getvalue()
        return png_bytes


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
        self._model = _resolve_version_ref(self._client, model or settings.replicate_image_model)

    def _render_depth_map(self, scene: trimesh.Scene, camera_pose: dict | None) -> bytes:
        scene_copy = scene.copy()
        if camera_pose:
            scene_copy.set_camera(
                angles=camera_pose.get("angles", (1.2, 0, 0)),
                distance=camera_pose.get("distance", 10.0),
                center=camera_pose.get("center", scene_copy.centroid),
            )
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

        output = self._client.run(
            self._model,
            input={
                "control_image": depth_file,
                "prompt": style_prompt or "photorealistic interior, natural daylight, 35mm lens",
                "guidance": 10,
                "num_inference_steps": 28,
            },
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
