from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Project
from ..security import resolve_in_roots


class ProjectError(ValueError):
    pass


def create_project(db: Session, name: str, path: str, description: str, specification: str,
                   test_command: str, *, import_existing: bool) -> Project:
    resolved = resolve_in_roots(path, get_settings().roots)
    if import_existing:
        if not resolved.is_dir():
            raise ProjectError("directory does not exist")
    else:
        if resolved.exists() and any(resolved.iterdir()):
            raise ProjectError("directory already exists and is not empty; use import instead")
        resolved.mkdir(parents=True, exist_ok=True)
    if db.scalar(select(Project).where((Project.name == name) | (Project.path == str(resolved)))):
        raise ProjectError("a project with that name or path already exists")
    p = Project(name=name, path=str(resolved), description=description, specification=specification,
                test_command=test_command)
    db.add(p)
    db.flush()
    return p


def project_path(p: Project) -> Path:
    return resolve_in_roots(p.path, get_settings().roots)
