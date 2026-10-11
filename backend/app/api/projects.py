from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.models.schemas import FloorPlanGeometry, Project, ProjectStatus
from app.pipeline.convert import ensure_png
from app.pipeline.cv_extract import refine_geometry_with_cv
from app.pipeline.geometry import export_glb
from app.pipeline.parser import get_parser
from app.pipeline.redact import redact_pii
from app.pipeline.render import get_renderer
from app.pipeline.validate import validate_room_topology
from app.storage import project_store

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = logging.getLogger(__name__)

_MAX_PARSE_ATTEMPTS = 3
_GEOMETRY_VALIDATION_STANDARDS = {
    "Raum-Topologie",
    "Wand-Topologie",
    "Öffnungs-Topologie",
    "Geometrie-Konsistenz",
    "Möbel-Topologie",
}


def _parse_with_retries(content: bytes, media_type: str) -> FloorPlanGeometry:
    """Ruft den Parser mit Retries auf - aus zwei unabhaengigen Gruenden:

    1. Transiente Infrastrukturfehler (z.B. Replicate-Deployment-Timeouts bei
       komplexen Plaenen mit vielen Raeumen/Moebeln) sind retriable, keine
       Code-Fehler.
    2. Das Parsing ist nicht deterministisch (siehe FINDINGS.md) - sich
       ueberlappende Raeume (z.B. ein faelschlich ins Gebaeudeinnere
       gesetzter Balkon) sind ein eindeutig erkennbarer Fehler, den ein
       erneuter Versuch oft behebt, da jeder Durchlauf leicht anders ausfaellt.

    Die Pixelrekonstruktion und die Parser-Geometrie werden als getrennte
    Kandidaten bewertet; automatische Wandnetz-Topologieableitung bleibt
    bewusst deaktiviert, weil sie an komplexen Plaenen falsch-positive
    Raumgrenzen erzeugen kann. Geometriewarnungen werden sichtbar gespeichert
    und koennen die Modell-Erzeugung als vorlaeufig kennzeichnen, statt
    ungeprueft als masshaltig zu gelten.

    Begrenzt auf _MAX_PARSE_ATTEMPTS, um Kosten/Latenz kontrollierbar zu
    halten. Bleibt am Ende trotzdem ein Geometriefehler bestehen, wird er
    als compliance_flag sichtbar gemacht statt verschwiegen.
    """
    parser = get_parser()
    best_geometry: FloorPlanGeometry | None = None
    best_quality_score = float("inf")
    last_exc: Exception | None = None

    def quality_score(geometry: FloorPlanGeometry) -> int:
        return sum(
            {"error": 100, "warning": 1}.get(flag.severity, 0)
            for flag in validate_room_topology(geometry)
        )

    for attempt in range(_MAX_PARSE_ATTEMPTS):
        try:
            geometry = parser.parse_floorplan(content, media_type=media_type)
        except Exception as exc:  # noqa: BLE001 - transiente Fehler retryen, sonst weiterreichen
            last_exc = exc
            is_last_attempt = attempt == _MAX_PARSE_ATTEMPTS - 1
            # Nur abbrechen, wenn wir noch GAR kein brauchbares Ergebnis haben
            # - ein frueherer erfolgreicher Versuch soll nicht wegen eines
            # transienten Fehlers im letzten Retry verworfen werden.
            if is_last_attempt or best_geometry is not None:
                break
            time.sleep(2)
            continue

        # Die Pixelrekonstruktion ist eine unabhaengige Geometriehypothese.
        # Sie ersetzt das Parser-Ergebnis nur, wenn sie die unabhaengigen
        # Geometriepruefungen mindestens ebenso gut besteht.
        candidates = [geometry]
        try:
            refined = refine_geometry_with_cv(content, geometry)
        except Exception:  # noqa: BLE001 - Bildanalyse ist optional, nie blockierend
            logger.warning(
                "Pixelbasierte Geometrieverfeinerung fehlgeschlagen; Parser-Geometrie bleibt Kandidat",
                exc_info=True,
            )
            refined = None
        if refined is not None:
            candidates.insert(0, refined)
        candidate = min(candidates, key=quality_score)
        candidate_score = quality_score(candidate)
        if candidate_score < best_quality_score:
            best_geometry, best_quality_score = candidate, candidate_score
        if not any(
            flag.severity == "error" for flag in validate_room_topology(candidate)
        ):
            break

    if best_geometry is None:
        raise last_exc if last_exc is not None else RuntimeError("Parsing fehlgeschlagen")

    best_geometry.compliance_flags = [
        *[
            flag
            for flag in best_geometry.compliance_flags
            if flag.standard not in _GEOMETRY_VALIDATION_STANDARDS
        ],
        *validate_room_topology(best_geometry),
    ]
    return best_geometry


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
    del raw_content  # Original-Bytes ab hier nicht mehr verwenden (siehe redact.py)

    try:
        # DSGVO/Datenschutz: Grundriss-Schriftfelder enthalten oft Namen/
        # Adressen/Kontaktdaten (Architekt, Bauherr/Eigentuemer). Schwaerzung
        # erfolgt VOR jeder Speicherung und VOR dem Parser-Aufruf - das
        # unredigierte Bild wird an keiner Stelle persistiert oder an einen
        # externen Parser-Provider geschickt. Siehe pipeline/redact.py fuer
        # die Methode und ihre (dokumentierten) Grenzen.
        redacted_content = redact_pii(png_content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PII-Schwärzung fehlgeschlagen: {exc}") from exc
    del png_content  # unredigiertes PNG ab hier nicht mehr verwenden

    filename = f"{original_filename.rsplit('.', 1)[0]}.png"
    project_store.save_floorplan_upload(project_id, filename, redacted_content)

    try:
        geometry = _parse_with_retries(redacted_content, media_type)
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

    geometry_flags = validate_room_topology(project.geometry)
    project.geometry = project.geometry.model_copy(
        update={
            "compliance_flags": [
                flag
                for flag in project.geometry.compliance_flags
                if flag.standard not in _GEOMETRY_VALIDATION_STANDARDS
            ]
            + geometry_flags
        }
    )

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
