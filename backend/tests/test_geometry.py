from app.models.schemas import (
    FloorPlanGeometry,
    Opening,
    OpeningType,
    Point2D,
    Room,
    RoomType,
    Wall,
)
from app.pipeline.geometry import build_scene, export_glb


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
