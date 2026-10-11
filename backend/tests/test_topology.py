from app.models.schemas import FloorPlanGeometry, Point2D, Room, RoomType, Wall
from app.pipeline.topology import derive_room_polygons
from app.pipeline.validate import find_room_overlaps


def _wall(id_, x0, y0, x1, y1, thickness=0.25, exterior=False):
    return Wall(
        id=id_,
        start=Point2D(x=x0, y=y0),
        end=Point2D(x=x1, y=y1),
        thickness_m=thickness,
        height_m=2.5,
        is_exterior=exterior,
    )


def test_derives_non_overlapping_rooms_matching_live_bug_scenario():
    """Regressionstest fuer den Live-Bug (docs/ARCHITECTURE.md): Der Parser
    lieferte ein Balkon-Polygon, das INNERHALB des Wohnzimmer-Polygons lag,
    obwohl die Waende selbst eine klar abgegrenzte Balkon-Nische im Norden
    des Gebaeudes bilden (Wandnetz ist korrekt, nur die vom Parser separat
    gelieferten Raumpolygone widersprechen sich). derive_room_polygons()
    muss beide Raeume korrekt und ueberlappungsfrei aus dem Wandnetz ableiten.
    """
    walls = [
        # Aussenwaende: 9m x 8m Gebaeude
        _wall("ext1", 0, 0, 9, 0, exterior=True),
        _wall("ext2", 9, 0, 9, 8, exterior=True),
        _wall("ext3", 9, 8, 0, 8, exterior=True),
        _wall("ext4", 0, 8, 0, 0, exterior=True),
        # Innenwand trennt Wohnzimmer (Sueden) vom Rest
        _wall("int1", 0, 4, 9, 4, thickness=0.12),
        # Balkon-Nische im Norden (Staple-Form, "stapelt" auf die Nordwand):
        # bildet zusammen mit dem Nordwand-Abschnitt zwischen x=1 und x=5
        # eine geschlossene Flaeche.
        _wall("balc1", 1, 0, 1, 2, thickness=0.1),
        _wall("balc2", 1, 2, 5, 2, thickness=0.1),
        _wall("balc3", 5, 2, 5, 0, thickness=0.1),
    ]

    # Parser-Fehler (wie im Live-Bug): Balkon-Polygon liegt faelschlich
    # INNERHALB des Wohnzimmer-Polygons statt in der Nische im Norden.
    wohnzimmer = Room(
        id="r1", name="Wohnzimmer", type=RoomType.living_room,
        polygon=[Point2D(x=0, y=4), Point2D(x=9, y=4), Point2D(x=9, y=8), Point2D(x=0, y=8)],
        area_m2=36.0,
    )
    balkon_falsch = Room(
        id="r2", name="Balkon", type=RoomType.balcony,
        polygon=[Point2D(x=2, y=5), Point2D(x=4, y=5), Point2D(x=4, y=7), Point2D(x=2, y=7)],
        area_m2=8.0,
    )
    geo = FloorPlanGeometry(walls=walls, rooms=[wohnzimmer, balkon_falsch])

    # Vorbedingung: Der Bug ist im Rohzustand tatsaechlich reproduziert (die
    # vom Parser gelieferte Balkon-Position liegt faelschlich im Wohnzimmer).
    assert len(find_room_overlaps(geo)) == 1

    corrected = derive_room_polygons(geo)

    corrected_rooms = {r.id: r for r in corrected.rooms}
    balkon_corrected = corrected_rooms["r2"]
    wohnzimmer_corrected = corrected_rooms["r1"]

    # Balkon muss jetzt in der Nische im Norden liegen (y zwischen 0 und 2),
    # NICHT mehr im urspruenglich falschen Bereich (y zwischen 5 und 7).
    balkon_ys = [p.y for p in balkon_corrected.polygon]
    assert max(balkon_ys) <= 2.1

    # Die beiden abgeleiteten Raeume duerfen sich nicht ueberlappen.
    assert find_room_overlaps(corrected) == []

    # Plausible Flaechen (Nische ca. 4x2m abzueglich Wandanteile).
    assert 6.0 < balkon_corrected.area_m2 < 8.5
    assert wohnzimmer_corrected.area_m2 > 30.0


def test_room_without_matching_wall_enclosure_keeps_original_polygon():
    """Ein Raum, der sich nicht aus dem Wandnetz ableiten laesst (z.B. eine
    offene Terrasse ohne vollstaendige Umwandung), behaelt seine Original-
    Geometrie - mit einem erklaerenden info-Flag statt eines stillen Fehlers.
    """
    walls = [
        _wall("ext1", 0, 0, 5, 0, exterior=True),
        _wall("ext2", 5, 0, 5, 5, exterior=True),
        _wall("ext3", 5, 5, 0, 5, exterior=True),
        _wall("ext4", 0, 5, 0, 0, exterior=True),
    ]
    room = Room(
        id="r1", name="Terrasse", type=RoomType.balcony,
        polygon=[Point2D(x=10, y=10), Point2D(x=12, y=10), Point2D(x=12, y=12), Point2D(x=10, y=12)],
        area_m2=4.0,
    )
    geo = FloorPlanGeometry(walls=walls, rooms=[room])

    corrected = derive_room_polygons(geo)

    # Original-Polygon bleibt erhalten (kein Void an dieser Stelle).
    assert corrected.rooms[0].polygon == room.polygon
    assert any(f.standard == "Geometrie-Ableitung" for f in corrected.compliance_flags)
