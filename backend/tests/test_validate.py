from app.models.schemas import FloorPlanGeometry, Point2D, Room, RoomType
from app.pipeline.validate import find_room_overlaps


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
