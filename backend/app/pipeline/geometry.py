"""FloorPlanGeometry -> 3D-Mesh (GLB).

Bewusst deterministisch und NICHT generativ (docs/ARCHITECTURE.md): Jede Wand,
jede Oeffnung, jeder Raum wird direkt aus den geparsten Koordinaten extrudiert.
Dasselbe GLB wird fuer die 3D-Tour (Three.js) UND als Geometrie-Grundlage fuer
die fotorealistische Render-Stufe verwendet - es gibt keine zweite, abweichende
3D-Repraesentation.
"""
from __future__ import annotations

import io
import math

import numpy as np
import trimesh
from shapely.geometry import Polygon

from app.models.schemas import FloorPlanGeometry, Room, RoomType, Wall

ROOM_COLORS: dict[RoomType, list[int]] = {
    RoomType.living_room: [230, 210, 180, 255],
    RoomType.bedroom: [200, 220, 230, 255],
    RoomType.kitchen: [220, 230, 200, 255],
    RoomType.bathroom: [210, 230, 230, 255],
    RoomType.hallway: [225, 225, 215, 255],
    RoomType.storage: [205, 205, 205, 255],
    RoomType.balcony: [200, 215, 180, 255],
    RoomType.other: [215, 215, 215, 255],
}

WALL_COLOR = [245, 245, 240, 255]
WINDOW_COLOR = [150, 200, 230, 120]


def _wall_direction(wall: Wall) -> tuple[np.ndarray, np.ndarray, float]:
    start = np.array([wall.start.x, wall.start.y])
    end = np.array([wall.end.x, wall.end.y])
    vec = end - start
    length = float(np.linalg.norm(vec))
    direction = vec / length if length > 1e-9 else np.array([1.0, 0.0])
    return start, direction, length


def _box_between(
    p0: np.ndarray, p1: np.ndarray, thickness: float, z0: float, z1: float, direction: np.ndarray
) -> trimesh.Trimesh:
    """Baut eine Box entlang der Segmentlinie p0->p1 mit gegebener Dicke/Hoehe."""
    normal = np.array([-direction[1], direction[0]])
    length = float(np.linalg.norm(p1 - p0))
    if length <= 1e-6:
        length = 1e-3
    box = trimesh.creation.box(extents=[length, thickness, max(z1 - z0, 1e-3)])

    # box ist zentriert um Ursprung entlang X; rotiere auf die Wandrichtung und
    # verschiebe auf Mittelpunkt des Segments.
    angle = math.atan2(direction[1], direction[0])
    rotation = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    box.apply_transform(rotation)

    midpoint = (p0 + p1) / 2.0
    translation = trimesh.transformations.translation_matrix(
        [midpoint[0], midpoint[1], (z0 + z1) / 2.0]
    )
    box.apply_transform(translation)
    del normal  # bereits in der Box-Rotation implizit beruecksichtigt
    return box


def _build_wall_mesh(wall: Wall) -> list[trimesh.Trimesh]:
    """Extrudiert eine Wand, mit echten Luecken an Tuer-/Fensterpositionen.

    Oeffnungen werden als Segment-Unterteilung umgesetzt: Tueren erzeugen eine
    volle Luecke (Boden bis Oeffnungshoehe), Fenster erzeugen eine Luecke nur
    im Brüstungs-/Sturzbereich; der Rest der Wand bleibt massiv.
    """
    start, direction, length = _wall_direction(wall)
    pieces: list[trimesh.Trimesh] = []

    # Segmentgrenzen entlang der Wand sammeln (Opening-Start/-Ende), sortiert.
    cuts = sorted(
        (
            (max(o.position_on_wall_m, 0.0), min(o.position_on_wall_m + o.width_m, length), o)
            for o in wall.openings
        ),
        key=lambda t: t[0],
    )

    cursor = 0.0
    for seg_start, seg_end, opening in cuts:
        if seg_start > cursor + 1e-6:
            p0 = start + direction * cursor
            p1 = start + direction * seg_start
            pieces.append(_box_between(p0, p1, wall.thickness_m, 0.0, wall.height_m, direction))

        p0 = start + direction * seg_start
        p1 = start + direction * seg_end
        if opening.sill_height_m > 1e-6:
            # Fenster: massiver Sockel bis zur Bruestung
            pieces.append(_box_between(p0, p1, wall.thickness_m, 0.0, opening.sill_height_m, direction))
        lintel_bottom = opening.sill_height_m + opening.height_m
        if lintel_bottom < wall.height_m - 1e-6:
            # Sturzbereich bis Deckenhoehe
            pieces.append(
                _box_between(p0, p1, wall.thickness_m, lintel_bottom, wall.height_m, direction)
            )
        cursor = seg_end

    if cursor < length - 1e-6:
        p0 = start + direction * cursor
        p1 = start + direction * length
        pieces.append(_box_between(p0, p1, wall.thickness_m, 0.0, wall.height_m, direction))

    if not pieces:
        pieces.append(
            _box_between(start, start + direction * length, wall.thickness_m, 0.0, wall.height_m, direction)
        )

    for piece in pieces:
        piece.visual.vertex_colors = WALL_COLOR
    return pieces


def _build_room_floor(room: Room) -> trimesh.Trimesh | None:
    points = [(p.x, p.y) for p in room.polygon]
    if len(points) < 3:
        return None
    polygon_2d = Polygon(points)
    if not polygon_2d.is_valid or polygon_2d.area <= 1e-6:
        return None
    mesh = trimesh.creation.extrude_polygon(polygon_2d, height=0.03)
    mesh.visual.vertex_colors = ROOM_COLORS.get(room.type, ROOM_COLORS[RoomType.other])
    return mesh


def build_scene(geometry: FloorPlanGeometry) -> trimesh.Scene:
    scene = trimesh.Scene()

    for wall in geometry.walls:
        for i, piece in enumerate(_build_wall_mesh(wall)):
            scene.add_geometry(piece, node_name=f"wall_{wall.id}_{i}")

    for room in geometry.rooms:
        floor = _build_room_floor(room)
        if floor is not None:
            scene.add_geometry(floor, node_name=f"floor_{room.id}")

    return scene


# glTF/GLB (und damit three.js/react-three-fiber im Frontend) erwartet laut
# Spezifikation Y-up. Unsere interne Geometrie ist Z-up (Hoehe = Z-Achse,
# Grundriss liegt in der XY-Ebene, siehe build_scene). trimesh exportiert
# die Szene unveraendert, OHNE diese Konvertierung - ohne die Rotation hier
# "steht" das flache Gebaeude im Viewer hochkant auf der Kante (sieht aus
# wie ein Regal statt wie ein Grundriss). Die Konvertierung betrifft NUR den
# GLB-Export; build_scene() selbst bleibt Z-up fuer Renderer/Kamera-Berechnungen.
_Z_UP_TO_Y_UP = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])


def _polygon_area(room: Room) -> float:
    pts = [(p.x, p.y) for p in room.polygon]
    poly = Polygon(pts)
    return poly.area if poly.is_valid else 0.0


_PREFERRED_INTERIOR_TYPES = (
    RoomType.living_room,
    RoomType.kitchen,
    RoomType.bedroom,
    RoomType.bathroom,
)


def pick_main_room(geometry: FloorPlanGeometry, room_id: str | None = None) -> Room | None:
    """Waehlt den Raum fuer die Innenraum-Kameraperspektive (render.py).

    Ohne explizite room_id wird der groesste Raum unter den "echten"
    Wohnraum-Typen gewaehlt (Wohnzimmer/Kueche/Schlafzimmer/Bad). Typen wie
    "other" (z.B. ein offener Innenhof ohne durchgehende Waende) oder
    Flur/Abstellraum/Balkon werden bewusst gemieden, da sie fuer ein
    Marketing-Rendering ("fotorealistische Darstellung der Zimmer") selten
    die gewuenschte Aufnahme ergeben.
    """
    if not geometry.rooms:
        return None
    if room_id is not None:
        for room in geometry.rooms:
            if room.id == room_id:
                return room
    preferred = [r for r in geometry.rooms if r.type in _PREFERRED_INTERIOR_TYPES]
    candidates = preferred or geometry.rooms
    return max(candidates, key=_polygon_area)


def interior_camera_transform(
    room: Room, eye_height: float = 1.6, look_height: float = 1.3
) -> np.ndarray:
    """Kamera-Pose fuer eine Innenraumaufnahme (Z-up, wie build_scene()).

    Steht ca. 0.9m von der am weitesten vom Raumzentrum entfernten Ecke
    entfernt (grob: "Blick von einer Raumecke zur gegenueberliegenden
    Wand") statt einer Aussen-/Vogelperspektive auf das gesamte Gebaeude -
    sonst interpretiert das Fotorealismus-Modell die kompakte Aussenform
    als Moebelstueck statt als Rauminnenansicht (siehe docs/ARCHITECTURE.md
    "Live-Testergebnis" fuer den beobachteten Fehlerfall).
    """
    poly_pts = np.array([[p.x, p.y] for p in room.polygon])
    centroid = poly_pts.mean(axis=0)
    dists = np.linalg.norm(poly_pts - centroid, axis=1)
    corner = poly_pts[int(np.argmax(dists))]

    to_center = centroid - corner
    norm = np.linalg.norm(to_center)
    direction = to_center / norm if norm > 1e-6 else np.array([1.0, 0.0])
    eye_xy = corner + direction * min(0.9, norm * 0.3)

    eye = np.array([eye_xy[0], eye_xy[1], eye_height])
    target = np.array([centroid[0], centroid[1], look_height])

    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, world_up)
    if np.linalg.norm(right) < 1e-6:
        right = np.array([1.0, 0.0, 0.0])
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)

    # Trimesh/OpenGL-Kamerakonvention: Kamera blickt entlang der lokalen -Z-Achse.
    transform = np.eye(4)
    transform[:3, 0] = right
    transform[:3, 1] = true_up
    transform[:3, 2] = -forward
    transform[:3, 3] = eye
    return transform


def export_glb(geometry: FloorPlanGeometry) -> bytes:
    scene = build_scene(geometry)
    scene.apply_transform(_Z_UP_TO_Y_UP)
    buffer = io.BytesIO()
    scene.export(file_obj=buffer, file_type="glb")
    return buffer.getvalue()
