"""Dateibasierte Projekt-Ablage. Fuer das MVP bewusst ohne DB-Abhaengigkeit -
ein Projekt pro Unterordner unter settings.storage_dir, Metadaten als JSON.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.models.schemas import Project


def _project_dir(project_id: str) -> Path:
    settings = get_settings()
    return settings.storage_dir / project_id


def _meta_path(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def create_project(name: str) -> Project:
    project = Project(id=str(uuid.uuid4()), name=name)
    _project_dir(project.id).mkdir(parents=True, exist_ok=True)
    save_project(project)
    return project


def save_project(project: Project) -> None:
    _project_dir(project.id).mkdir(parents=True, exist_ok=True)
    _meta_path(project.id).write_text(project.model_dump_json(indent=2), encoding="utf-8")


def get_project(project_id: str) -> Project | None:
    path = _meta_path(project_id)
    if not path.exists():
        return None
    return Project.model_validate_json(path.read_text(encoding="utf-8"))


def list_projects() -> list[Project]:
    settings = get_settings()
    if not settings.storage_dir.exists():
        return []
    projects = []
    for entry in settings.storage_dir.iterdir():
        if entry.is_dir() and (entry / "project.json").exists():
            projects.append(Project.model_validate_json((entry / "project.json").read_text(encoding="utf-8")))
    return sorted(projects, key=lambda p: p.id)


def save_floorplan_upload(project_id: str, filename: str, content: bytes) -> Path:
    directory = _project_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"floorplan_{filename}"
    path.write_bytes(content)
    return path


def floorplan_path(project_id: str, filename: str) -> Path:
    return _project_dir(project_id) / f"floorplan_{filename}"


def save_model_glb(project_id: str, glb_bytes: bytes) -> Path:
    path = _project_dir(project_id) / "model.glb"
    path.write_bytes(glb_bytes)
    return path


def model_glb_path(project_id: str) -> Path:
    return _project_dir(project_id) / "model.glb"


def save_render_preview(project_id: str, index: int, png_bytes: bytes) -> Path:
    path = preview_path(project_id, index)
    path.write_bytes(png_bytes)
    return path


def preview_path(project_id: str, index: int) -> Path:
    return _project_dir(project_id) / f"preview_{index}.png"
