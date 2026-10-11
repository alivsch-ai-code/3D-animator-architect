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

from app.models.schemas import FloorPlanGeometry, Opening, OpeningType, Room, RoomType, Wall

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
WINDOW_GLASS_COLOR = [190, 215, 225, 255]
WINDOW_FRAME_COLOR = [250, 250, 248, 255]
DOOR_LEAF_COLOR = [150, 110, 75, 255]
FURNITURE_WOOD = [140, 105, 72, 255]
FURNITURE_UPHOLSTERY = [120, 130, 140, 255]
FURNITURE_COUNTER = [225, 225, 222, 255]

# Mindest-Innenmass (Breite/Tiefe in m), ab dem ein Raumtyp ueberhaupt
# moebliert wird - verhindert, dass Moebel in zu kleinen/schmalen Raeumen
# (z.B. Fehlinterpretationen des Parsers) mit den Waenden ueberlappen.
_MIN_ROOM_FOR_FURNITURE = 1.6


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


def _build_door_leaf(p0: np.ndarray, p1: np.ndarray, opening: Opening) -> trimesh.Trimesh:
    """Tuerblatt, am Anfang der Oeffnung angeschlagen und in den Raum geschwenkt
    (fester Oeffnungswinkel) - macht die Tuer im Modell/Rendering als
    tatsaechliches Objekt sichtbar statt nur als Wandluecke.
    """
    opening_vec = p1 - p0
    width = float(np.linalg.norm(opening_vec)) or opening.width_m
    wall_dir = opening_vec / width if width > 1e-6 else np.array([1.0, 0.0])

    swing_angle = math.radians(62)
    cos_a, sin_a = math.cos(swing_angle), math.sin(swing_angle)
    # 2D-Rotation der Wandrichtung um den Anschlagpunkt p0.
    leaf_dir = np.array(
        [wall_dir[0] * cos_a - wall_dir[1] * sin_a, wall_dir[0] * sin_a + wall_dir[1] * cos_a]
    )
    leaf_width = width * 0.92
    leaf_end = p0 + leaf_dir * leaf_width

    leaf = _box_between(p0, leaf_end, thickness=0.04, z0=0.02, z1=opening.height_m, direction=leaf_dir)
    leaf.visual.vertex_colors = DOOR_LEAF_COLOR
    return leaf


def _build_window_pane(p0: np.ndarray, p1: np.ndarray, wall: Wall, opening: Opening) -> list[trimesh.Trimesh]:
    """Verglasung + Rahmen fuer eine Fensteroeffnung, mittig in der Wand."""
    z0 = opening.sill_height_m
    z1 = opening.sill_height_m + opening.height_m
    _, direction, _ = _wall_direction(wall)

    frame = _box_between(p0, p1, thickness=wall.thickness_m * 0.9, z0=z0, z1=z1, direction=direction)
    frame.visual.vertex_colors = WINDOW_FRAME_COLOR

    inset = np.maximum((p1 - p0) * 0.04, np.zeros(2))
    glass = _box_between(
        p0 + inset, p1 - inset, thickness=wall.thickness_m * 0.3, z0=z0 + 0.05, z1=z1 - 0.05, direction=direction
    )
    glass.visual.vertex_colors = WINDOW_GLASS_COLOR
    return [frame, glass]


def _build_wall_mesh(wall: Wall) -> tuple[list[trimesh.Trimesh], list[trimesh.Trimesh]]:
    """Extrudiert eine Wand, mit echten Luecken an Tuer-/Fensterpositionen.

    Oeffnungen werden als Segment-Unterteilung umgesetzt: Tueren erzeugen eine
    volle Luecke (Boden bis Oeffnungshoehe), Fenster erzeugen eine Luecke nur
    im Brüstungs-/Sturzbereich; der Rest der Wand bleibt massiv. Zusaetzlich
    werden sichtbare Tuerblaetter/Fensterverglasungen erzeugt (zweiter
    Rueckgabewert), statt die Oeffnung nur als leere Luecke zu zeigen -
    sonst wirkt das Modell/Rendering leer und nicht "kundenzeigbar".
    """
    start, direction, length = _wall_direction(wall)
    pieces: list[trimesh.Trimesh] = []
    extras: list[trimesh.Trimesh] = []

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

        if opening.type == OpeningType.door:
            extras.append(_build_door_leaf(p0, p1, opening))
        else:
            extras.extend(_build_window_pane(p0, p1, wall, opening))

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
    return pieces, extras


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


def _room_bbox(room: Room) -> tuple[float, float, float, float]:
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _place_box(cx: float, cy: float, w: float, d: float, z0: float, z1: float, color: list[int]) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=[w, d, max(z1 - z0, 1e-3)])
    box.apply_translation([cx, cy, (z0 + z1) / 2.0])
    box.visual.vertex_colors = color
    return box


def _build_furniture(room: Room) -> list[trimesh.Trimesh]:
    """Einfache, box-basierte Platzhaltermoebel pro Raumtyp.

    Bewusst grobe Blockout-Geometrie, keine detaillierten Modelle (siehe
    docs/ARCHITECTURE.md) - der Zweck ist zweifach: (1) die begehbare Tour
    wirkt nicht leer/unverkaeuflich, (2) die Depth-Map fuers fotorealistische
    Rendering (render.py) bekommt dadurch echte Moebel-Silhouetten an der
    richtigen Stelle statt eines leeren Raums, den FLUX sonst frei
    "halluzinieren" muesste.

    Platzierung ist heuristisch (Bounding-Box-basiert, gegen die "Suedwand"
    = min-Y-Kante), nicht an die tatsaechliche Raumform angepasst - fuer
    ueberwiegend rechteckige Raeume (Regelfall) ausreichend plausibel.
    """
    minx, miny, maxx, maxy = _room_bbox(room)
    width, depth = maxx - minx, maxy - miny
    if min(width, depth) < _MIN_ROOM_FOR_FURNITURE:
        return []

    margin = 0.15
    cx = (minx + maxx) / 2.0
    pieces: list[trimesh.Trimesh] = []

    if room.type == RoomType.bedroom:
        bed_w, bed_d, bed_h = min(1.6, width - 2 * margin), min(2.0, depth * 0.6), 0.5
        bed_cy = miny + margin + bed_d / 2.0
        pieces.append(_place_box(cx, bed_cy, bed_w, bed_d, 0.0, bed_h, FURNITURE_WOOD))
        if width - bed_w > 0.7:
            nightstand_cx = cx + bed_w / 2.0 + 0.3
            pieces.append(_place_box(nightstand_cx, bed_cy, 0.4, 0.4, 0.0, 0.5, FURNITURE_WOOD))

    elif room.type == RoomType.living_room:
        sofa_w, sofa_d, sofa_h = min(2.0, width - 2 * margin), 0.85, 0.75
        sofa_cy = miny + margin + sofa_d / 2.0
        pieces.append(_place_box(cx, sofa_cy, sofa_w, sofa_d, 0.0, sofa_h, FURNITURE_UPHOLSTERY))
        table_cy = sofa_cy + sofa_d / 2.0 + 0.6
        if table_cy + 0.3 < maxy - margin:
            pieces.append(_place_box(cx, table_cy, 1.0, 0.5, 0.0, 0.4, FURNITURE_WOOD))

    elif room.type == RoomType.kitchen:
        counter_w = min(width - 2 * margin, 3.0)
        counter_cy = miny + margin + 0.3
        pieces.append(_place_box(cx, counter_cy, counter_w, 0.6, 0.0, 0.9, FURNITURE_COUNTER))

    elif room.type == RoomType.bathroom:
        vanity_cx = minx + margin + 0.3
        vanity_cy = miny + margin + 0.225
        pieces.append(_place_box(vanity_cx, vanity_cy, 0.6, 0.45, 0.0, 0.85, FURNITURE_COUNTER))

    return pieces


def build_scene(geometry: FloorPlanGeometry) -> trimesh.Scene:
    scene = trimesh.Scene()

    for wall in geometry.walls:
        pieces, extras = _build_wall_mesh(wall)
        for i, piece in enumerate(pieces):
            scene.add_geometry(piece, node_name=f"wall_{wall.id}_{i}")
        for i, extra in enumerate(extras):
            scene.add_geometry(extra, node_name=f"opening_{wall.id}_{i}")

    for room in geometry.rooms:
        for i, item in enumerate(_build_furniture(room)):
            scene.add_geometry(item, node_name=f"furniture_{room.id}_{i}")

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
    eye_xy = corner + direction * min(1.1, norm * 0.35)

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
