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
Plan zu erkennen sind. Wenn ein Mass unsicher ist, nutze eine plausible Schaetzung \
gemaess der unten stehenden Referenz und vermerke die Unsicherheit in source_notes \
statt zu raten und es als sicher auszugeben.

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
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude-Antwort ist kein valides JSON: {exc}\nRohtext: {raw_text[:500]}") from exc

        try:
            return FloorPlanGeometry.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Claude-JSON entspricht nicht dem FloorPlanGeometry-Schema: {exc}") from exc
