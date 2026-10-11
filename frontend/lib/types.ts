// Spiegelt backend/app/models/schemas.py - siehe docs/ARCHITECTURE.md
// fuer die IFC-orientierte Begruendung des Schemas.

export interface Point2D {
  x: number;
  y: number;
}

export type OpeningType = "door" | "window";

export interface Opening {
  type: OpeningType;
  position_on_wall_m: number;
  width_m: number;
  height_m: number;
  sill_height_m: number;
}

export interface Wall {
  id: string;
  start: Point2D;
  end: Point2D;
  thickness_m: number;
  height_m: number;
  is_exterior: boolean;
  openings: Opening[];
}

export type RoomType =
  | "living_room"
  | "bedroom"
  | "kitchen"
  | "bathroom"
  | "hallway"
  | "storage"
  | "balcony"
  | "other";

export interface Room {
  id: string;
  name: string;
  type: RoomType;
  polygon: Point2D[];
  area_m2: number | null;
}

export interface ComplianceFlag {
  severity: "info" | "warning" | "error";
  standard: string;
  message: string;
  related_element_id: string | null;
}

export interface FloorPlanGeometry {
  scale_hint: string | null;
  walls: Wall[];
  rooms: Room[];
  compliance_flags: ComplianceFlag[];
  source_notes: string | null;
}

export type ProjectStatus =
  | "created"
  | "uploaded"
  | "parsed"
  | "model_generated"
  | "rendered"
  | "failed";

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  floorplan_filename: string | null;
  geometry: FloorPlanGeometry | null;
  model_glb_path: string | null;
  render_preview_paths: string[];
}

export const ROOM_TYPE_LABELS: Record<RoomType, string> = {
  living_room: "Wohnzimmer",
  bedroom: "Schlafzimmer",
  kitchen: "Küche",
  bathroom: "Bad",
  hallway: "Flur",
  storage: "Abstellraum",
  balcony: "Balkon",
  other: "Sonstiges",
};

export const STATUS_LABELS: Record<ProjectStatus, string> = {
  created: "Angelegt",
  uploaded: "Hochgeladen",
  parsed: "Grundriss analysiert",
  model_generated: "3D-Modell erzeugt",
  rendered: "Gerendert",
  failed: "Fehlgeschlagen",
};
