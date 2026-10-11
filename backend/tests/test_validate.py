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
from app.pipeline.validate import find_room_overlaps, validate_room_topology


def test_no_overlap_for_adjacent_rooms():
    room_a = Room(
        id="a", name="A", type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=3, y=0), Point2D(x=3, y=3), Point2D(x=0, y=3)],
        area_m2=9.0,
    )
    room_b = Room(
        id="b", name="B", type=RoomType.bedroom,
        polygon=[Point2D(x=3, y=0), Point2D(x=6, y=0), Point2D(x=6, y=3), Point2D(x=3, y=3)],
        area_m2=9.0,
    )
    geo = FloorPlanGeometry(walls=[], rooms=[room_a, room_b])

    assert find_room_overlaps(geo) == []


def test_detects_room_fully_contained_in_another():
    """Regressionstest fuer den Live-Bug: ein Balkon-Polygon wurde faelschlich
    INNERHALB des Wohnzimmer-Polygons platziert statt ausserhalb der Fassade.
    """
    living_room = Room(
        id="r1", name="Wohnzimmer", type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=6, y=0), Point2D(x=6, y=6), Point2D(x=0, y=6)],
        area_m2=36.0,
    )
    balcony = Room(
        id="r2", name="Balkon", type=RoomType.balcony,
        polygon=[Point2D(x=1, y=1), Point2D(x=3, y=1), Point2D(x=3, y=3), Point2D(x=1, y=3)],
        area_m2=4.0,
    )
    geo = FloorPlanGeometry(walls=[], rooms=[living_room, balcony])

    flags = find_room_overlaps(geo)

    assert len(flags) == 1
    assert flags[0].severity == "error"
    assert "Wohnzimmer" in flags[0].message
    assert "Balkon" in flags[0].message


def test_small_edge_overlap_tolerance_is_not_flagged():
    """Minimale Ueberlappung an einer gemeinsamen Wand (Rundungstoleranz)
    soll NICHT als Fehler gelten.
    """
    room_a = Room(
        id="a", name="A", type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=3, y=0), Point2D(x=3, y=3), Point2D(x=0, y=3)],
        area_m2=9.0,
    )
    room_b = Room(
        id="b", name="B", type=RoomType.bedroom,
        polygon=[Point2D(x=2.98, y=0), Point2D(x=6, y=0), Point2D(x=6, y=3), Point2D(x=2.98, y=3)],
        area_m2=9.0,
    )
    geo = FloorPlanGeometry(walls=[], rooms=[room_a, room_b])

    assert find_room_overlaps(geo) == []


def test_validate_room_topology_flags_invalid_polygon_geometry():
    room = Room(
        id="bad", name="Bad polygon", type=RoomType.bathroom,
        polygon=[Point2D(x=0, y=0), Point2D(x=1, y=1), Point2D(x=0, y=1), Point2D(x=1, y=0)],
        area_m2=0.5,
    )
    geo = FloorPlanGeometry(walls=[], rooms=[room])

    flags = validate_room_topology(geo)

    assert any(flag.standard == "Raum-Topologie" for flag in flags)


def test_validate_room_topology_flags_large_area_mismatches():
    living_room = Room(
        id="living",
        name="Wohnzimmer",
        type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=3.71, y=0), Point2D(x=3.71, y=5.82), Point2D(x=0, y=5.82)],
        area_m2=27.79,
    )
    bathroom = Room(
        id="bath",
        name="Bad",
        type=RoomType.bathroom,
        polygon=[Point2D(x=4, y=0), Point2D(x=7.27, y=0), Point2D(x=7.27, y=2.95), Point2D(x=4, y=2.95)],
        area_m2=5.61,
    )
    geometry = FloorPlanGeometry(walls=[], rooms=[living_room, bathroom])

    flags = validate_room_topology(geometry)
    area_flags = {flag.related_element_id: flag for flag in flags if flag.standard == "Raum-Topologie"}

    assert area_flags["living"].severity == "warning"
    assert area_flags["bath"].severity == "error"


def test_validate_room_topology_flags_opening_outside_wall():
    wall = Wall(
        id="w1",
        start=Point2D(x=0, y=0),
        end=Point2D(x=2, y=0),
        thickness_m=0.2,
        openings=[
            Opening(
                type=OpeningType.door,
                position_on_wall_m=1.5,
                width_m=0.9,
                height_m=2.0,
            )
        ],
    )
    geometry = FloorPlanGeometry(walls=[wall], rooms=[])

    flags = validate_room_topology(geometry)

    assert any(flag.standard == "Öffnungs-Topologie" and flag.severity == "error" for flag in flags)


def test_validate_room_topology_flags_overlapping_openings():
    wall = Wall(
        id="w1",
        start=Point2D(x=0, y=0),
        end=Point2D(x=4, y=0),
        thickness_m=0.2,
        openings=[
            Opening(type=OpeningType.window, position_on_wall_m=0.5, width_m=1.5, height_m=1.2, sill_height_m=0.9),
            Opening(type=OpeningType.window, position_on_wall_m=1.8, width_m=1.0, height_m=1.2, sill_height_m=0.9),
        ],
    )
    geometry = FloorPlanGeometry(walls=[wall], rooms=[])

    flags = validate_room_topology(geometry)

    assert any("überschneiden" in flag.message for flag in flags)


def test_validate_room_topology_flags_furniture_center_outside_room():
    room = Room(
        id="r1",
        name="Wohnzimmer",
        type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=3, y=0), Point2D(x=3, y=3), Point2D(x=0, y=3)],
        area_m2=9.0,
    )
    sofa = FurnitureItem(
        type=FurnitureType.sofa,
        room_id="r1",
        center=Point2D(x=4.0, y=1.5),
        width_m=2.0,
        depth_m=0.9,
    )
    geometry = FloorPlanGeometry(walls=[], rooms=[room], furniture=[sofa])

    flags = validate_room_topology(geometry)

    assert any(flag.standard == "Möbel-Topologie" and flag.severity == "warning" for flag in flags)
