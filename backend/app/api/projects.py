from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.models.schemas import FloorPlanGeometry, Project, ProjectStatus
from app.pipeline.convert import ensure_png
from app.pipeline.geometry import export_glb
from app.pipeline.parser import get_parser
from app.pipeline.render import get_renderer
from app.storage import project_store

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_or_404(project_id: str) -> Project:
    project = project_store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    return project


@router.post("", response_model=Project)
def create_project(name: str) -> Project:
    return project_store.create_project(name)


@router.get("", response_model=list[Project])
def list_projects() -> list[Project]:
    return project_store.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    return _get_or_404(project_id)


@router.post("/{project_id}/floorplan", response_model=Project)
async def upload_floorplan(project_id: str, file: UploadFile) -> Project:
    project = _get_or_404(project_id)
    raw_content = await file.read()
    original_filename = file.filename or "upload.png"

    try:
        # PDF-Uploads (uebliches Format bei Maklern) werden einheitlich zu PNG
        # konvertiert (erste Seite) - siehe pipeline/convert.py.
        png_content, media_type = ensure_png(raw_content, file.content_type, original_filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Datei konnte nicht gelesen werden: {exc}") from exc

    filename = f"{original_filename.rsplit('.', 1)[0]}.png"
    project_store.save_floorplan_upload(project_id, filename, png_content)

    try:
        parser = get_parser()
        geometry = parser.parse_floorplan(png_content, media_type=media_type)
    except Exception as exc:  # noqa: BLE001 - dem Nutzer den konkreten Parsing-Fehler zeigen
        project.status = ProjectStatus.failed
        project_store.save_project(project)
        raise HTTPException(status_code=502, detail=f"Grundriss-Parsing fehlgeschlagen: {exc}") from exc

    project.floorplan_filename = filename
    project.geometry = geometry
    project.status = ProjectStatus.parsed
    project_store.save_project(project)
    return project


@router.get("/{project_id}/floorplan")
def get_floorplan_image(project_id: str) -> FileResponse:
    project = _get_or_404(project_id)
    if not project.floorplan_filename:
        raise HTTPException(status_code=404, detail="Kein Grundriss hochgeladen")
    path = project_store.floorplan_path(project_id, project.floorplan_filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(path)


@router.put("/{project_id}/geometry", response_model=Project)
def update_geometry(project_id: str, geometry: FloorPlanGeometry) -> Project:
    """Erlaubt Korrektur der geparsten Geometrie vor der 3D-Erzeugung."""
    project = _get_or_404(project_id)
    project.geometry = geometry
    project_store.save_project(project)
    return project


@router.post("/{project_id}/model", response_model=Project)
def generate_model(project_id: str) -> Project:
    project = _get_or_404(project_id)
    if project.geometry is None:
        raise HTTPException(status_code=400, detail="Projekt hat noch keine geparste Geometrie")

    try:
        glb_bytes = export_glb(project.geometry)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"3D-Modell-Erzeugung fehlgeschlagen: {exc}") from exc

    project_store.save_model_glb(project_id, glb_bytes)
    project.model_glb_path = str(project_store.model_glb_path(project_id))
    project.status = ProjectStatus.model_generated
    project_store.save_project(project)
    return project


@router.get("/{project_id}/model.glb")
def get_model(project_id: str) -> FileResponse:
    project = _get_or_404(project_id)
    path = project_store.model_glb_path(project_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Noch kein 3D-Modell generiert")
    return FileResponse(path, media_type="model/gltf-binary")


@router.post("/{project_id}/render", response_model=Project)
def render_preview(project_id: str, style_prompt: str = "", room_id: str | None = None) -> Project:
    project = _get_or_404(project_id)
    if project.geometry is None:
        raise HTTPException(status_code=400, detail="Projekt hat noch keine geparste Geometrie")

    from app.pipeline.geometry import build_scene, interior_camera_transform, pick_main_room

    scene = build_scene(project.geometry)
    room = pick_main_room(project.geometry, room_id=room_id)
    if room is None:
        raise HTTPException(status_code=400, detail="Keine Raeume in der Geometrie vorhanden")
    camera_pose = {"transform": interior_camera_transform(room)}

    renderer = get_renderer()
    try:
        png_bytes = renderer.render(scene, camera_pose=camera_pose, style_prompt=style_prompt)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Rendering fehlgeschlagen: {exc}") from exc

    index = len(project.render_preview_paths)
    path = project_store.save_render_preview(project_id, index, png_bytes)
    project.render_preview_paths.append(str(path))
    project.status = ProjectStatus.rendered
    project_store.save_project(project)
    return project


@router.get("/{project_id}/preview/{index}.png")
def get_preview(project_id: str, index: int) -> FileResponse:
    _get_or_404(project_id)
    path = project_store.preview_path(project_id, index)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Vorschaubild nicht gefunden")
    return FileResponse(path, media_type="image/png")
