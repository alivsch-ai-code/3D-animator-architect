"""Grundriss-Parsing: Bild -> FloorPlanGeometry via Claude Vision.

Architekturentscheidung (docs/LLM-DECISION.md): Das LLM liefert die STRUKTURIERTEN
PARAMETER (Wandkoordinaten, Oeffnungen, Raeume), nicht die Bild-Pixel. Die exakte
3D-Geometrie wird anschliessend deterministisch in geometry.py konstruiert.
"""
from __future__ import annotations

import base64
import json
from typing import Protocol

from anthropic import Anthropic
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.standards_context import load_standards_context
from app.models.schemas import FloorPlanGeometry

SYSTEM_PROMPT_TEMPLATE = """\
Du bist ein Senior-Architekt und Bauzeichner-Experte. Du analysierst einen \
2D-Grundriss (Haus oder Wohnung) und extrahierst daraus EXAKTE, strukturierte \
Geometriedaten fuer eine deterministische 3D-Rekonstruktion.

Kritische Regel: Deine Ausgabe muss die reale Geometrie des Plans so genau wie \
moeglich wiedergeben - erfinde keine Waende, Tueren oder Fenster, die nicht im \
Plan zu erkennen sind (also keine Raeume/Elemente hinzufuegen, die nicht im Bild \
vorhanden sind). Wenn ein Mass unsicher ist, nutze eine plausible Schaetzung \
gemaess der unten stehenden Referenz und vermerke die Unsicherheit in source_notes \
statt zu raten und es als sicher auszugeben.

Sehr wichtig - gib NIEMALS eine leere walls/rooms-Liste zurueck, nur weil kein \
Massstab oder keine Masskette im Bild steht: Die meisten realen Grundrisse \
(gerade aeltere oder informelle) haben keine expliziten Zahlen. Schaetze in \
diesem Fall den Massstab aus typischen Raumgroessen und den sichtbaren \
Proportionen im Bild (z.B. Schlafzimmer ca. 3x3 bis 4x4m, Bad ca. 2x2m, \
Wohnzimmer/Wohnkueche ca. 4x5m, Flur-Breite ca. 1-1.5m, Tuerbreite ca. 0.8-0.9m \
als Referenzgroesse im Bild) und wende diesen geschaetzten Massstab konsistent \
auf den gesamten Plan an. Setze scale_hint dann auf eine Beschreibung wie \
"geschaetzt, kein Massstab im Plan angegeben" und erklaere die Schaetzgrundlage \
in source_notes. Eine vollstaendige, geometrisch stimmige Schaetzung ist immer \
nuetzlicher als eine leere Antwort.

Nutze bei der Interpretation folgende Referenz (Normen & Praxiskonventionen):

{standards_context}

Gib ausschliesslich ein einziges JSON-Objekt zurueck, das exakt diesem Schema \
entspricht (keine Erklaerungen, kein Markdown, kein Codeblock):

{{
  "scale_hint": "string oder null, z.B. '1:100'",
  "walls": [
    {{
      "id": "string, z.B. 'w1'",
      "start": {{"x": float, "y": float}},
      "end": {{"x": float, "y": float}},
      "thickness_m": float,
      "height_m": float,
      "is_exterior": bool,
      "openings": [
        {{
          "type": "door" | "window",
          "position_on_wall_m": float,
          "width_m": float,
          "height_m": float,
          "sill_height_m": float
        }}
      ]
    }}
  ],
  "rooms": [
    {{
      "id": "string, z.B. 'r1'",
      "name": "string, z.B. 'Wohnzimmer'",
      "type": "living_room" | "bedroom" | "kitchen" | "bathroom" | "hallway" | "storage" | "balcony" | "other",
      "polygon": [{{"x": float, "y": float}}, ...],
      "area_m2": float oder null
    }}
  ],
  "compliance_flags": [
    {{"severity": "info" | "warning" | "error", "standard": "string, z.B. 'DIN 18040-2'", "message": "string", "related_element_id": "string oder null"}}
  ],
  "source_notes": "string oder null"
}}

Koordinaten (x, y) sind in Metern relativ zu einem beliebigen, aber fuer den \
gesamten Plan konsistenten Ursprung. Nutze den erkannten Massstab/die Masskette \
zur Kalibrierung - das hat Vorrang vor einer reinen Pixel-Schaetzung.
"""


class LLMClient(Protocol):
    """Austauschbare Schnittstelle, siehe docs/LLM-DECISION.md ("kein Lock-in")."""

    def parse_floorplan(self, image_bytes: bytes, media_type: str) -> FloorPlanGeometry: ...


class ClaudeFloorPlanParser:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._client = Anthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model or settings.parser_model

    def parse_floorplan(self, image_bytes: bytes, media_type: str = "image/png") -> FloorPlanGeometry:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(standards_context=load_standards_context())
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = self._client.messages.create(
            model=self._model,
            max_tokens=8000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Analysiere diesen Grundriss und gib die exakte "
                                "strukturierte Geometrie als JSON zurueck."
                            ),
                        },
                    ],
                }
            ],
        )

        raw_text = "".join(block.text for block in response.content if block.type == "text")
        return self._validate(raw_text)

    @staticmethod
    def _validate(raw_text: str) -> FloorPlanGeometry:
        return _parse_json_response(raw_text, source="Claude")


def _resolve_version_ref(client, model_slug: str) -> str:
    """Manche Community-Modelle auf Replicate akzeptieren den "owner/name"-Shortcut
    nicht direkt (404) und brauchen eine versions-gepinnte Referenz
    "owner/name:version". Loest das automatisch auf, falls noch kein ":" enthalten ist.
    """
    if ":" in model_slug:
        return model_slug
    owner, name = model_slug.split("/", 1)
    model = client.models.get(f"{owner}/{name}")
    return f"{owner}/{name}:{model.latest_version.id}"


def _parse_json_response(raw_text: str, source: str) -> FloorPlanGeometry:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source}-Antwort ist kein valides JSON: {exc}\nRohtext: {raw_text[:500]}") from exc

    try:
        return FloorPlanGeometry.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{source}-JSON entspricht nicht dem FloorPlanGeometry-Schema: {exc}") from exc


class GeminiFloorPlanParser:
    """Alternative Parser-Implementierung mit Google Gemini (eigener API-Key).

    Nutzt dieselbe Schema- und Normen-Vorgabe wie der Claude-Parser - nur der
    Modellanbieter unterscheidet sich. Siehe docs/LLM-DECISION.md: Claude Opus 5
    bleibt die Empfehlung, Gemini ist als austauschbares Backend verfuegbar,
    z.B. zum Kostenvergleich oder falls bereits ein Gemini-Key vorhanden ist.

    Hinweis: Der Gemini-Modellname (`gemini_parser_model`) sollte vor produktivem
    Einsatz gegen die aktuelle Google-AI-Studio-Modellliste geprueft werden, da
    sich Modell-IDs bei Google regelmaessig aendern.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        from google import genai

        self._client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self._model = model or settings.gemini_parser_model

    def parse_floorplan(self, image_bytes: bytes, media_type: str = "image/png") -> FloorPlanGeometry:
        from google.genai import types

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(standards_context=load_standards_context())
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                "Analysiere diesen Grundriss und gib die exakte strukturierte Geometrie als JSON zurueck.",
            ],
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return _parse_json_response(response.text, source="Gemini")


def _build_replicate_input(model_slug: str, data_uri: str, user_text: str, system_prompt: str) -> dict:
    """Input-Feldnamen sind auf Replicate je Modell(-familie) unterschiedlich
    benannt - diese Adapter-Funktion kapselt das. Live getestet am
    2026-10-11 gegen backend/tests/fixtures/floorplans/davies_house_1951.png,
    Ergebnisse/Screenshots in tests/fixtures/floorplans/model_comparison/:
    anthropic/claude-opus-4.6 lieferte dabei klar die geometrisch plausibelste
    Ausgabe (echte, unterschiedliche Raumproportionen statt Platzhalter-Raster),
    bei vergleichbarer Laufzeit (~50s) zu google/gemini-3.1-pro. Ein 30B-
    Open-Weights-Modell (internvl3.5-30b) wurde ebenfalls getestet: deutlich
    schlechtere, raeumlich inkohaerente Ausgabe UND mit $0.47/~8min pro Lauf
    unverhaeltnismaessig teuer/langsam - absichtlich NICHT als Option
    vorgesehen, siehe docs/LLM-DECISION.md.
    """
    full_prompt = f"{system_prompt}\n\n{user_text}"

    if model_slug.startswith("anthropic/"):
        return {
            "image": data_uri,
            "prompt": user_text,
            "system_prompt": system_prompt,
            "max_tokens": 8000,
            "max_image_resolution": 1.5,
        }
    if model_slug.startswith("google/gemini"):
        return {
            "images": [data_uri],
            "prompt": user_text,
            "system_instruction": system_prompt,
            "max_output_tokens": 20000,
        }
    # Generischer Fallback (z.B. lucataco/qwen3-vl-*): kein system_prompt-Feld,
    # daher alles in den Prompt gepackt.
    return {
        "media": data_uri,
        "prompt": full_prompt,
        "max_new_tokens": 4096,
        "temperature": 0.1,
    }


class ReplicateFloorPlanParser:
    """Parser ueber auf Replicate gehostete Modelle - sowohl offene
    Open-Weights-Modelle als auch proprietaere Modelle wie Claude/Gemini, die
    Replicate selbst als gehostete Endpunkte anbietet (kein separater
    Anthropic-/Google-Key noetig, siehe docs/LLM-DECISION.md).

    Empfehlung/Standard: anthropic/claude-opus-4.6 - siehe
    _build_replicate_input() fuer die Live-Testergebnisse, die zu dieser
    Empfehlung gefuehrt haben.
    """

    def __init__(self, api_token: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        import replicate as replicate_sdk

        self._client = replicate_sdk.Client(api_token=api_token or settings.replicate_api_token)
        self._model_slug = model or settings.replicate_parser_model
        self._model = _resolve_version_ref(self._client, self._model_slug)

    def parse_floorplan(self, image_bytes: bytes, media_type: str = "image/png") -> FloorPlanGeometry:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{media_type};base64,{image_b64}"
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(standards_context=load_standards_context())
        user_text = (
            "Analysiere diesen Grundriss und gib die exakte strukturierte "
            "Geometrie als JSON zurueck."
        )

        input_payload = _build_replicate_input(self._model_slug, data_uri, user_text, system_prompt)
        output = self._client.run(self._model, input=input_payload)
        raw_text = "".join(output) if not isinstance(output, str) else output
        return _parse_json_response(raw_text, source="Replicate")


def get_parser() -> LLMClient:
    """Factory: waehlt die Parser-Implementierung nach settings.parser_provider."""
    settings = get_settings()
    if settings.parser_provider == "gemini":
        return GeminiFloorPlanParser()
    if settings.parser_provider == "replicate":
        return ReplicateFloorPlanParser()
    return ClaudeFloorPlanParser()
