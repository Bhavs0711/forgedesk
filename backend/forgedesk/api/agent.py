from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..agent.approvals import broker
from ..agent.runner import AgentManager, RunnerError
from ..config import anthropic_api_key_configured, get_settings
from ..db import get_db
from ..models import Approval, ApprovalStatus, Project
from ..services import runtime_settings
from ..services.testing import docker_available
from ..ws import hub
from .deps import project_or_404

router = APIRouter(prefix="/api", tags=["agent"])


def manager(request: Request) -> AgentManager:
    return request.app.state.agents


@router.get("/projects/{project_id}/agent")
def status(p: Project = Depends(project_or_404), m: AgentManager = Depends(manager)) -> dict:
    return m.status(p.id)


@router.post("/projects/{project_id}/agent/{action}")
async def control(action: str, p: Project = Depends(project_or_404), m: AgentManager = Depends(manager)) -> dict:
    runner = m.runner(p.id)
    try:
        if action == "start":
            runner.start()
        elif action == "pause":
            await runner.pause()
        elif action == "resume":
            await runner.resume()
        elif action == "stop":
            await runner.stop()
        else:
            raise HTTPException(404, "unknown action")
    except RunnerError as e:
        raise HTTPException(409, str(e)) from e
    return runner.snapshot()


@router.get("/projects/{project_id}/approvals", response_model=list[schemas.ApprovalOut])
def pending_approvals(p: Project = Depends(project_or_404), db: Session = Depends(get_db)) -> list[Approval]:
    live = set(broker._waiters)  # only approvals an agent is actually waiting on
    rows = db.scalars(select(Approval).where(Approval.project_id == p.id, Approval.status == ApprovalStatus.pending))
    return [a for a in rows if a.id in live]


@router.post("/approvals/{approval_id}/{decision}", status_code=204)
def decide(approval_id: int, decision: str) -> None:
    if decision not in ("approve", "deny"):
        raise HTTPException(404, "unknown decision")
    if not broker.decide(approval_id, decision == "approve"):
        raise HTTPException(409, "no agent is waiting on this approval (it may have expired)")


@router.get("/settings", response_model=schemas.SettingsOut)
def get_settings_view(db: Session = Depends(get_db)) -> schemas.SettingsOut:
    s, lim = get_settings(), runtime_settings.load(db)
    return schemas.SettingsOut(api_key_configured=anthropic_api_key_configured(), docker_available=docker_available(),
                               docker_enabled=s.use_docker, workspace_roots=[str(r) for r in s.roots], model=lim.model,
                               max_session_minutes=lim.max_session_minutes, max_turns_per_session=lim.max_turns_per_session,
                               max_consecutive_failures=lim.max_consecutive_failures, auto_commit=lim.auto_commit)


@router.put("/settings", response_model=schemas.SettingsOut)
def update_settings(body: schemas.SettingsUpdate, db: Session = Depends(get_db)) -> schemas.SettingsOut:
    runtime_settings.save(db, body.model_dump())
    return get_settings_view(db)


ws_router = APIRouter()


@ws_router.websocket("/ws/projects/{project_id}")
async def project_socket(ws: WebSocket, project_id: int) -> None:
    await hub.connect(project_id, ws)
    try:
        await ws.send_json({"type": "agent_status", "project_id": project_id,
                            "data": ws.app.state.agents.status(project_id)})
        while True:
            await ws.receive_text()  # clients only listen; this detects disconnects
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(project_id, ws)
