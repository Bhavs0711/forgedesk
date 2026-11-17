from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Feature, Project


def project_or_404(project_id: int, db: Session = Depends(get_db)) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def feature_or_404(db: Session, project_id: int, feature_id: int) -> Feature:
    f = db.get(Feature, feature_id)
    if not f or f.project_id != project_id:
        raise HTTPException(404, "feature not found")
    return f
