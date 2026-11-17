from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import AgentSession, Feature, Project, SessionEvent, TestRun
from ..security import PathNotAllowed
from ..services import features as feat
from ..services import git, reports
from ..services.projects import ProjectError, create_project, project_path
from ..services.testing import run_project_tests
from .deps import feature_or_404, project_or_404

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _feature_out(db: Session, f: Feature, deps: dict[int, set[int]]) -> schemas.FeatureOut:
    out = schemas.FeatureOut.model_validate(f)
    out.depends_on = sorted(deps.get(f.id, ()))
    return out


@router.get("", response_model=list[dict])
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    rows = []
    for p in db.scalars(select(Project).order_by(Project.name)):
        rows.append({**schemas.ProjectOut.model_validate(p).model_dump(mode="json"), "progress": feat.progress(db, p.id)})
    return rows


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create(body: schemas.ProjectCreate, db: Session = Depends(get_db)) -> Project:
    try:
        return create_project(db, body.name, body.path, body.description, body.specification, body.test_command,
                              import_existing=body.import_existing)
    except (ProjectError, PathNotAllowed) as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{project_id}", response_model=dict)
def detail(p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> dict:
    return {**schemas.ProjectOut.model_validate(p).model_dump(mode="json"), "progress": feat.progress(db, p.id)}


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update(body: schemas.ProjectUpdate, p: Project = Depends(project_or_404)) -> Project:
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    return p


@router.delete("/{project_id}", status_code=204)
def delete(p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> Response:
    """Removes ForgeDesk's records only. The project directory is never deleted."""
    db.delete(p)
    return Response(status_code=204)


@router.get("/{project_id}/features", response_model=list[schemas.FeatureOut])
def list_features(p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> list[schemas.FeatureOut]:
    deps = feat.dependency_map(db, p.id)
    feats = db.scalars(select(Feature).where(Feature.project_id == p.id).order_by(Feature.priority, Feature.sequence, Feature.id))
    return [_feature_out(db, f, deps) for f in feats]


@router.post("/{project_id}/features", response_model=schemas.FeatureOut, status_code=201)
def add_feature(body: schemas.FeatureCreate, p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> schemas.FeatureOut:
    if db.scalar(select(Feature.id).where(Feature.project_id == p.id, Feature.title == body.title)):
        raise HTTPException(409, "a feature with that title already exists")
    f = Feature(project_id=p.id, **body.model_dump())
    db.add(f)
    db.flush()
    return _feature_out(db, f, {})


@router.patch("/{project_id}/features/{feature_id}", response_model=schemas.FeatureOut)
def edit_feature(feature_id: int, body: schemas.FeatureUpdate, p: Project = Depends(project_or_404),
                 db: Session = Depends(get_db)) -> schemas.FeatureOut:
    f = feature_or_404(db, p.id, feature_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(f, k, v)
    return _feature_out(db, f, feat.dependency_map(db, p.id))


@router.put("/{project_id}/features/{feature_id}/status", response_model=schemas.FeatureOut)
def set_status(feature_id: int, body: schemas.StatusUpdate, p: Project = Depends(project_or_404),
               db: Session = Depends(get_db)) -> schemas.FeatureOut:
    feature_or_404(db, p.id, feature_id)
    try:
        f = feat.set_status_manually(db, feature_id, body.status)
    except feat.FeatureError as e:
        raise HTTPException(409, str(e)) from e
    return _feature_out(db, f, feat.dependency_map(db, p.id))


@router.put("/{project_id}/features/{feature_id}/dependencies/{depends_on_id}", status_code=204)
def add_dep(feature_id: int, depends_on_id: int, p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> Response:
    feature_or_404(db, p.id, feature_id)
    try:
        feat.add_dependency(db, feature_id, depends_on_id)
    except feat.FeatureError as e:
        raise HTTPException(400, str(e)) from e
    return Response(status_code=204)


@router.delete("/{project_id}/features/{feature_id}/dependencies/{depends_on_id}", status_code=204)
def remove_dep(feature_id: int, depends_on_id: int, p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> Response:
    feature_or_404(db, p.id, feature_id)
    feat.remove_dependency(db, feature_id, depends_on_id)
    return Response(status_code=204)


@router.get("/{project_id}/sessions", response_model=list[schemas.SessionOut])
def sessions(p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> list[AgentSession]:
    return list(db.scalars(select(AgentSession).where(AgentSession.project_id == p.id).order_by(AgentSession.id.desc()).limit(100)))


@router.get("/{project_id}/events", response_model=list[schemas.EventOut])
def events(limit: int = 200, session_id: int | None = None, p: Project = Depends(project_or_404),
           db: Session = Depends(get_db)) -> list[SessionEvent]:
    q = select(SessionEvent).where(SessionEvent.project_id == p.id)
    if session_id is not None:
        q = q.where(SessionEvent.session_id == session_id)
    rows = list(db.scalars(q.order_by(SessionEvent.id.desc()).limit(min(limit, 1000))))
    return rows[::-1]


@router.get("/{project_id}/tests", response_model=list[schemas.TestRunOut])
def tests(p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> list[TestRun]:
    return list(db.scalars(select(TestRun).where(TestRun.project_id == p.id).order_by(TestRun.id.desc()).limit(50)))


@router.post("/{project_id}/regression", response_model=schemas.TestRunOut)
async def regression(p: Project = Depends(project_or_404)) -> TestRun:
    try:
        return await run_project_tests(p.id, project_path(p), p.test_command, kind="regression")
    except (ValueError, PathNotAllowed) as e:
        raise HTTPException(400, str(e)) from e


@router.get("/{project_id}/git")
async def git_log(p: Project = Depends(project_or_404)) -> dict:
    path = project_path(p)
    return {"is_repo": await git.is_repo(path), "log": await git.log(path), "status": await git.status(path)}


@router.post("/{project_id}/git/init", status_code=204)
async def git_init(p: Project = Depends(project_or_404)) -> Response:
    await git.ensure_repo(project_path(p))
    return Response(status_code=204)


@router.get("/{project_id}/report")
def report(format: str = "json", p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> Response:
    import json
    data = reports.build_report(db, p)
    if format == "md":
        return Response(reports.to_markdown(data), media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{p.name}-report.md"'})
    return Response(json.dumps(data, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{p.name}-report.json"'})
