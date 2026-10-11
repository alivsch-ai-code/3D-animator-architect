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
    position_on_wall_m: float = Field(..., ge=0, description="Abstand vom Wandanfang in Metern")
    width_m: float = Field(..., gt=0)
    height_m: float = Field(..., gt=0)
    sill_height_m: float = Field(0.0, ge=0, description="Brüstungshöhe, 0 für Türen")


class Wall(BaseModel):
    """Entspricht konzeptionell IfcWall / IfcWallStandardCase."""

    id: str
    start: Point2D
    end: Point2D
    thickness_m: float = Field(..., gt=0)
    height_m: float = Field(2.5, gt=0)
    is_exterior: bool = False
    openings: list[Opening] = Field(default_factory=list)


class FurnitureType(str, Enum):
    bed = "bed"
    sofa = "sofa"
    table = "table"
    chair = "chair"
    wardrobe = "wardrobe"
    kitchen_counter = "kitchen_counter"
    sink = "sink"
    bathtub = "bathtub"
    shower = "shower"
    toilet = "toilet"
    other = "other"


class FurnitureItem(BaseModel):
    """Moebel-/Sanitaersymbol, das BEREITS im Quellgrundriss eingezeichnet war.

    Eigenes Feld statt Teil der Wand-/Raumgeometrie: Viele reale Grundrisse
    (v.a. Makler-Exposés) zeichnen Moebel/Sanitaerobjekte (Sofa, Bett,
    Badewanne, Kueche) direkt mit ein. Ohne diese Trennung interpretiert der
    Parser Moebel-Umrisslinien leicht faelschlich als Wandsegmente ("komische
    Waende" an Moebelpositionen) - siehe docs/ARCHITECTURE.md Live-Testergebnis.
    """

    type: FurnitureType
    room_id: str | None = Field(None, description="ID des Raums, in dem das Moebel steht, falls zuordenbar")
    center: Point2D
    rotation_deg: float = Field(0.0, description="Rotation um die Hochachse, 0 = entlang X-Achse")
    width_m: float = Field(..., gt=0)
    depth_m: float = Field(..., gt=0)
    height_m: float | None = Field(None, gt=0, description="Falls nicht bekannt, nutzt geometry.py einen Typ-Default")


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
    furniture: list[FurnitureItem] = Field(
        default_factory=list,
        description="Im Quellplan bereits eingezeichnete Moebel/Sanitaerobjekte, falls vorhanden",
    )
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
