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
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from app.models.schemas import (
    FloorPlanGeometry,
    FurnitureItem,
    FurnitureType,
    Opening,
    OpeningType,
    Point2D,
    Room,
    RoomType,
    Wall,
)

ROOM_FLOOR_COLOR = [194, 181, 163, 255]
ROOM_COLORS: dict[RoomType, list[int]] = {room_type: ROOM_FLOOR_COLOR for room_type in RoomType}

WALL_COLOR = [245, 245, 240, 255]
WINDOW_GLASS_COLOR = [190, 215, 225, 255]
WINDOW_FRAME_COLOR = [250, 250, 248, 255]
DOOR_LEAF_COLOR = [150, 110, 75, 255]
FURNITURE_WOOD = [140, 105, 72, 255]
FURNITURE_UPHOLSTERY = [120, 130, 140, 255]
FURNITURE_COUNTER = [225, 225, 222, 255]
FURNITURE_SANITARY = [235, 238, 238, 255]
FURNITURE_MATTRESS = [220, 211, 195, 255]
FURNITURE_CUSHION = [177, 166, 150, 255]
FURNITURE_DARK_WOOD = [92, 66, 45, 255]
FURNITURE_METAL = [120, 126, 127, 255]

FURNITURE_COLORS: dict[FurnitureType, list[int]] = {
    FurnitureType.bed: FURNITURE_WOOD,
    FurnitureType.sofa: FURNITURE_UPHOLSTERY,
    FurnitureType.table: FURNITURE_WOOD,
    FurnitureType.chair: FURNITURE_WOOD,
    FurnitureType.wardrobe: FURNITURE_WOOD,
    FurnitureType.kitchen_counter: FURNITURE_COUNTER,
    FurnitureType.sink: FURNITURE_SANITARY,
    FurnitureType.bathtub: FURNITURE_SANITARY,
    FurnitureType.shower: FURNITURE_SANITARY,
    FurnitureType.toilet: FURNITURE_SANITARY,
    FurnitureType.other: FURNITURE_WOOD,
}

# Default-Hoehe (m) je Moebeltyp, falls der Parser keine height_m liefert.
_FURNITURE_DEFAULT_HEIGHT: dict[FurnitureType, float] = {
    FurnitureType.bed: 0.5,
    FurnitureType.sofa: 0.75,
    FurnitureType.table: 0.4,
    FurnitureType.chair: 0.45,
    FurnitureType.wardrobe: 1.9,
    FurnitureType.kitchen_counter: 0.9,
    FurnitureType.sink: 0.85,
    FurnitureType.bathtub: 0.5,
    FurnitureType.shower: 0.1,
    FurnitureType.toilet: 0.4,
    FurnitureType.other: 0.5,
}

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
    mesh = trimesh.creation.extrude_polygon(polygon_2d, height=0.08)
    mesh.apply_translation([0.0, 0.0, -0.04])
    mesh.visual.vertex_colors = ROOM_COLORS.get(room.type, ROOM_COLORS[RoomType.other])
    return mesh


def _room_bbox(room: Room) -> tuple[float, float, float, float]:
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _place_box(
    cx: float, cy: float, w: float, d: float, z0: float, z1: float, color: list[int], rotation_deg: float = 0.0
) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=[w, d, max(z1 - z0, 1e-3)])
    if rotation_deg:
        box.apply_transform(trimesh.transformations.rotation_matrix(math.radians(rotation_deg), [0, 0, 1]))
    box.apply_translation([cx, cy, (z0 + z1) / 2.0])
    box.visual.vertex_colors = color
    return box


def _point_in_polygon(point: Point2D, polygon: list[Point2D]) -> bool:
    return Polygon([(p.x, p.y) for p in polygon]).contains(ShapelyPoint(point.x, point.y))


def _assign_furniture_to_rooms(geometry: FloorPlanGeometry) -> dict[str, list[FurnitureItem]]:
    """Ordnet geparste Moebel-Items (parser.py::FurnitureItem) ihren Raeumen zu.

    Nutzt room_id, falls vom Parser gesetzt, sonst einen Punkt-in-Polygon-Test
    gegen die Raumpolygone als Fallback.
    """
    by_room: dict[str, list[FurnitureItem]] = {room.id: [] for room in geometry.rooms}
    for item in geometry.furniture:
        if item.room_id and item.room_id in by_room:
            by_room[item.room_id].append(item)
            continue
        for room in geometry.rooms:
            if _point_in_polygon(item.center, room.polygon):
                by_room[room.id].append(item)
                break
    return by_room


def _build_parsed_furniture_item(item: FurnitureItem) -> list[trimesh.Trimesh]:
    """Build recognizable, scale-bounded furniture from the plan's symbols.

    These meshes are intentionally deterministic and lightweight. They are a
    substantial improvement over one colored cuboid per symbol, but are not a
    substitute for licensed production furniture assets.
    """
    width = max(0.15, item.width_m)
    depth = max(0.15, item.depth_m)
    height = item.height_m or _FURNITURE_DEFAULT_HEIGHT.get(item.type, 0.5)
    cos_a = math.cos(math.radians(item.rotation_deg))
    sin_a = math.sin(math.radians(item.rotation_deg))
    meshes: list[trimesh.Trimesh] = []

    def add_box(
        offset_x: float,
        offset_y: float,
        part_width: float,
        part_depth: float,
        z0: float,
        z1: float,
        color: list[int],
    ) -> None:
        center_x = item.center.x + offset_x * cos_a - offset_y * sin_a
        center_y = item.center.y + offset_x * sin_a + offset_y * cos_a
        meshes.append(
            _place_box(
                center_x,
                center_y,
                part_width,
                part_depth,
                z0,
                z1,
                color,
                item.rotation_deg,
            )
        )

    def add_ellipsoid(
        offset_x: float,
        offset_y: float,
        center_z: float,
        radii: tuple[float, float, float],
        color: list[int],
    ) -> None:
        mesh = trimesh.creation.icosphere(subdivisions=2)
        mesh.apply_scale(radii)
        if item.rotation_deg:
            mesh.apply_transform(
                trimesh.transformations.rotation_matrix(
                    math.radians(item.rotation_deg), [0, 0, 1]
                )
            )
        mesh.apply_translation(
            [
                item.center.x + offset_x * cos_a - offset_y * sin_a,
                item.center.y + offset_x * sin_a + offset_y * cos_a,
                center_z,
            ]
        )
        mesh.visual.vertex_colors = color
        meshes.append(mesh)

    if item.type == FurnitureType.bed:
        frame_h = min(0.22, height * 0.42)
        mattress_h = min(0.22, max(0.12, height - frame_h))
        add_box(0, 0, width, depth, 0, frame_h, FURNITURE_DARK_WOOD)
        add_box(0, 0, width * 0.96, depth * 0.94, frame_h, frame_h + mattress_h, FURNITURE_MATTRESS)
        pillow_depth = min(0.36, depth * 0.22)
        pillow_width = width * 0.34
        for side in (-1, 1):
            add_box(
                side * width * 0.23,
                depth * 0.32,
                pillow_width,
                pillow_depth,
                frame_h + mattress_h,
                frame_h + mattress_h + 0.07,
                [238, 233, 222, 255],
            )
        add_box(0, depth * 0.48, width, 0.08, frame_h, min(height, frame_h + mattress_h + 0.35), FURNITURE_WOOD)
    elif item.type == FurnitureType.sofa:
        seat_h = min(0.42, height * 0.58)
        arm_w = min(0.2, width * 0.12)
        add_box(0, 0, width, depth, 0.12, seat_h, FURNITURE_DARK_WOOD)
        cushion_count = 2 if width < 1.8 else 3
        cushion_w = (width - 2 * arm_w) / cushion_count
        for index in range(cushion_count):
            x = -width / 2 + arm_w + cushion_w * (index + 0.5)
            add_box(x, -depth * 0.12, cushion_w * 0.94, depth * 0.65, seat_h, seat_h + 0.1, FURNITURE_CUSHION)
            add_box(x, depth * 0.28, cushion_w * 0.94, depth * 0.18, seat_h, height, FURNITURE_UPHOLSTERY)
        for side in (-1, 1):
            add_box(side * (width / 2 - arm_w / 2), 0, arm_w, depth, 0.12, height * 0.78, FURNITURE_UPHOLSTERY)
    elif item.type == FurnitureType.kitchen_counter:
        cabinet_h = min(0.78, height * 0.84)
        add_box(0, 0, width, depth, 0.08, cabinet_h, FURNITURE_COUNTER)
        add_box(0, 0, width * 1.03, depth * 1.08, cabinet_h, height, [205, 201, 193, 255])
        count = max(2, min(4, round(width / 0.55)))
        for index in range(count):
            x = -width / 2 + width * (index + 0.5) / count
            add_box(x, -depth / 2 - 0.006, width / count * 0.94, 0.012, 0.16, cabinet_h - 0.04, [213, 210, 203, 255])
            add_box(x + width / count * 0.31, -depth / 2 - 0.025, 0.018, 0.025, cabinet_h * 0.55, cabinet_h * 0.69, FURNITURE_METAL)
    elif item.type == FurnitureType.bathtub:
        rim = min(0.09, min(width, depth) * 0.14)
        base_h = min(0.48, height * 0.8)
        add_box(0, 0, width * 0.94, depth * 0.92, 0, base_h, FURNITURE_SANITARY)
        add_box(0, 0, width, depth, base_h, height, [246, 246, 242, 255])
        add_box(0, 0, width - 2 * rim, depth - 2 * rim, base_h + 0.015, base_h + 0.03, [184, 202, 205, 255])
    elif item.type == FurnitureType.toilet:
        base_h = min(0.42, height * 0.72)
        add_ellipsoid(0, -depth * 0.08, base_h * 0.62, (width * 0.48, depth * 0.36, base_h * 0.62), FURNITURE_SANITARY)
        add_box(0, depth * 0.32, width * 0.82, depth * 0.28, base_h, height, FURNITURE_SANITARY)
        add_ellipsoid(0, -depth * 0.08, base_h * 0.98, (width * 0.42, depth * 0.31, 0.035), [105, 110, 112, 255])
    elif item.type == FurnitureType.sink:
        cabinet_h = min(0.72, height * 0.82)
        add_box(0, 0, width, depth, 0.05, cabinet_h, [205, 199, 190, 255])
        add_box(0, 0, width * 1.04, depth * 1.05, cabinet_h, height, FURNITURE_SANITARY)
        add_ellipsoid(0, 0, height + 0.005, (width * 0.34, depth * 0.3, 0.035), [200, 213, 214, 255])
        add_box(0, depth * 0.34, 0.035, 0.035, height, height + 0.2, FURNITURE_METAL)
    elif item.type == FurnitureType.wardrobe:
        add_box(0, 0, width, depth, 0.04, height, FURNITURE_WOOD)
        add_box(0, -depth / 2 - 0.008, width * 0.48, 0.016, 0.08, height - 0.04, [158, 125, 91, 255])
        add_box(0, -depth / 2 - 0.03, 0.02, 0.025, height * 0.42, height * 0.56, FURNITURE_METAL)
    elif item.type == FurnitureType.table:
        top_h = min(0.76, height)
        leg = max(0.045, min(width, depth) * 0.055)
        add_box(0, 0, width, depth, top_h - 0.06, top_h, FURNITURE_WOOD)
        for x in (-width * 0.42, width * 0.42):
            for y in (-depth * 0.4, depth * 0.4):
                add_box(x, y, leg, leg, 0, top_h - 0.06, FURNITURE_DARK_WOOD)
    elif item.type == FurnitureType.chair:
        seat_h = min(0.48, height * 0.68)
        leg = max(0.035, min(width, depth) * 0.06)
        add_box(0, 0, width, depth, seat_h - 0.06, seat_h, FURNITURE_WOOD)
        add_box(0, depth * 0.4, width, leg, seat_h, height, FURNITURE_WOOD)
        for x in (-width * 0.4, width * 0.4):
            for y in (-depth * 0.38, depth * 0.38):
                add_box(x, y, leg, leg, 0, seat_h - 0.06, FURNITURE_DARK_WOOD)
    else:
        add_box(0, 0, width, depth, 0, height, FURNITURE_COLORS.get(item.type, FURNITURE_WOOD))

    return meshes


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

    # Echte, im Quellplan eingezeichnete Moebel (falls vom Parser erkannt)
    # haben Vorrang vor der generischen Platzhalter-Moeblierung pro Raum -
    # nur Raeume ohne zugeordnete Parser-Moebel bekommen den Fallback.
    furniture_by_room = _assign_furniture_to_rooms(geometry)
    for room in geometry.rooms:
        parsed_items = furniture_by_room.get(room.id, [])
        if parsed_items:
            meshes = [mesh for item in parsed_items for mesh in _build_parsed_furniture_item(item)]
        else:
            meshes = _build_furniture(room)
        for i, item in enumerate(meshes):
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
