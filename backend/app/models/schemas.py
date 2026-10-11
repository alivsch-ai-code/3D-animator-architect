"""Datenmodelle für die Grundriss-Pipeline.

Das Schema ist bewusst IFC-orientiert benannt (Wall/Opening/Room ~ IfcWall/
IfcOpeningElement/IfcSpace), siehe docs/STANDARDS.md Abschnitt 5, damit ein
späterer echter IFC-Export ohne Schema-Bruch möglich ist.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Point2D(BaseModel):
    x: float
    y: float


class OpeningType(str, Enum):
    door = "door"
    window = "window"


class Opening(BaseModel):
    """Tür oder Fenster, als Position entlang einer Wand."""

    type: OpeningType
    position_on_wall_m: float = Field(..., description="Abstand vom Wandanfang in Metern")
    width_m: float
    height_m: float
    sill_height_m: float = Field(0.0, description="Brüstungshöhe, 0 für Türen")


class Wall(BaseModel):
    """Entspricht konzeptionell IfcWall / IfcWallStandardCase."""

    id: str
    start: Point2D
    end: Point2D
    thickness_m: float
    height_m: float = 2.5
    is_exterior: bool = False
    openings: list[Opening] = Field(default_factory=list)


class RoomType(str, Enum):
    living_room = "living_room"
    bedroom = "bedroom"
    kitchen = "kitchen"
    bathroom = "bathroom"
    hallway = "hallway"
    storage = "storage"
    balcony = "balcony"
    other = "other"


class Room(BaseModel):
    """Entspricht konzeptionell IfcSpace."""

    id: str
    name: str
    type: RoomType
    polygon: list[Point2D] = Field(..., min_length=3)
    area_m2: float | None = Field(None, description="Nettofläche nach DIN 277 NUF, falls bekannt")


class ComplianceFlag(BaseModel):
    """Plausibilitäts-/Normkonflikt, vom Parser erkannt (siehe docs/STANDARDS.md)."""

    severity: str = Field(..., description="info | warning | error")
    standard: str = Field(..., description="z.B. 'DIN 18040-2'")
    message: str
    related_element_id: str | None = None


class FloorPlanGeometry(BaseModel):
    """Exaktes, strukturiertes Ergebnis der Grundriss-Parsing-Stufe."""

    scale_hint: str | None = Field(None, description="z.B. '1:100', falls im Plan erkannt")
    walls: list[Wall]
    rooms: list[Room]
    compliance_flags: list[ComplianceFlag] = Field(default_factory=list)
    source_notes: str | None = Field(
        None, description="Freitext-Hinweise des Parsers, z.B. unsichere Stellen"
    )


class ProjectStatus(str, Enum):
    created = "created"
    uploaded = "uploaded"
    parsed = "parsed"
    model_generated = "model_generated"
    rendered = "rendered"
    failed = "failed"


class Project(BaseModel):
    id: str
    name: str
    status: ProjectStatus = ProjectStatus.created
    floorplan_filename: str | None = None
    geometry: FloorPlanGeometry | None = None
    model_glb_path: str | None = None
    render_preview_paths: list[str] = Field(default_factory=list)
