import pytest

from app.models.schemas import (
    FloorPlanGeometry,
    Opening,
    OpeningType,
    Point2D,
    Room,
    RoomType,
    Wall,
)
from app.pipeline.geometry import (
    build_scene,
    export_glb,
    interior_camera_transform,
    pick_main_room,
)


def _sample_geometry() -> FloorPlanGeometry:
    return FloorPlanGeometry(
        scale_hint="1:100",
        walls=[
            Wall(
                id="w1",
                start=Point2D(x=0, y=0),
                end=Point2D(x=5, y=0),
                thickness_m=0.25,
                height_m=2.5,
                is_exterior=True,
                openings=[
                    Opening(
                        type=OpeningType.door,
                        position_on_wall_m=2.0,
                        width_m=0.9,
                        height_m=2.0,
                        sill_height_m=0.0,
                    )
                ],
            ),
            Wall(
                id="w2",
                start=Point2D(x=5, y=0),
                end=Point2D(x=5, y=4),
                thickness_m=0.25,
                height_m=2.5,
                is_exterior=True,
                openings=[
                    Opening(
                        type=OpeningType.window,
                        position_on_wall_m=1.0,
                        width_m=1.2,
                        height_m=1.2,
                        sill_height_m=0.9,
                    )
                ],
            ),
            Wall(id="w3", start=Point2D(x=5, y=4), end=Point2D(x=0, y=4), thickness_m=0.25, height_m=2.5, is_exterior=True),
            Wall(id="w4", start=Point2D(x=0, y=4), end=Point2D(x=0, y=0), thickness_m=0.25, height_m=2.5, is_exterior=True),
        ],
        rooms=[
            Room(
                id="r1",
                name="Wohnzimmer",
                type=RoomType.living_room,
                polygon=[Point2D(x=0, y=0), Point2D(x=5, y=0), Point2D(x=5, y=4), Point2D(x=0, y=4)],
                area_m2=20.0,
            )
        ],
    )


def test_build_scene_produces_expected_piece_count():
    scene = build_scene(_sample_geometry())
    # w1 (Tuer, sill=0): vor+nach Tuer + Sturz = 3
    # w2 (Fenster): vor+nach + Sockel + Sturz = 4
    # w3, w4: je 1 (keine Oeffnung)
    # + 1 Bodenplatte
    assert len(scene.geometry) == 3 + 4 + 1 + 1 + 1


def test_export_glb_roundtrips():
    import trimesh

    glb_bytes = export_glb(_sample_geometry())
    assert len(glb_bytes) > 0

    reloaded = trimesh.load(trimesh.util.wrap_as_stream(glb_bytes), file_type="glb")
    assert len(reloaded.geometry) == 10


def test_wall_without_openings_is_single_box():
    geo = _sample_geometry()
    scene = build_scene(FloorPlanGeometry(walls=[geo.walls[2]], rooms=[]))
    assert len(scene.geometry) == 1


def test_export_glb_is_y_up_not_z_up():
    """Regressionstest fuer den "Regal"-Bug (ARCHITECTURE.md Live-Testergebnis
    2026-10-11): glTF/GLB erwartet Y-up, unsere interne Geometrie ist Z-up.
    Nach dem Export muss die Wandhoehe (2.5m) auf der Y-Achse liegen, nicht
    auf der Z-Achse - sonst "steht" das Gebaeude im Viewer auf der Kante.
    """
    import trimesh

    geo = _sample_geometry()
    glb_bytes = export_glb(geo)
    reloaded = trimesh.load(trimesh.util.wrap_as_stream(glb_bytes), file_type="glb")
    extents = reloaded.bounds[1] - reloaded.bounds[0]

    assert extents[1] == pytest.approx(2.5, abs=0.1), "Hoehe sollte nach Y-up-Konvertierung auf Y liegen"
    assert extents[1] < extents[0], "Gebaeude sollte flach sein (Hoehe < Grundrissbreite), nicht hochkant"


def test_pick_main_room_prefers_living_spaces_over_other():
    """Regressionstest: 'other'/Hof-Raeume (z.B. ein unummauerter Innenhof)
    duerfen nicht als Hauptraum fuer die Innenraum-Kamera gewaehlt werden,
    auch wenn sie flaechenmaessig am groessten sind.
    """
    court = Room(
        id="r_court",
        name="Court",
        type=RoomType.other,
        polygon=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)],
        area_m2=100.0,
    )
    lounge = Room(
        id="r_lounge",
        name="Lounge",
        type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=4, y=0), Point2D(x=4, y=4), Point2D(x=0, y=4)],
        area_m2=16.0,
    )
    geo = FloorPlanGeometry(walls=[], rooms=[court, lounge])

    chosen = pick_main_room(geo)

    assert chosen is not None
    assert chosen.id == "r_lounge"


def test_pick_main_room_falls_back_when_no_living_space():
    only_room = Room(
        id="r_storage",
        name="Abstellraum",
        type=RoomType.storage,
        polygon=[Point2D(x=0, y=0), Point2D(x=2, y=0), Point2D(x=2, y=2), Point2D(x=0, y=2)],
        area_m2=4.0,
    )
    geo = FloorPlanGeometry(walls=[], rooms=[only_room])

    assert pick_main_room(geo).id == "r_storage"


def test_interior_camera_transform_is_inside_room_at_eye_height():
    room = Room(
        id="r1",
        name="Wohnzimmer",
        type=RoomType.living_room,
        polygon=[Point2D(x=0, y=0), Point2D(x=5, y=0), Point2D(x=5, y=4), Point2D(x=0, y=4)],
        area_m2=20.0,
    )
    transform = interior_camera_transform(room)
    eye = transform[:3, 3]

    assert eye[2] == pytest.approx(1.6)
    assert 0 <= eye[0] <= 5
    assert 0 <= eye[1] <= 4
