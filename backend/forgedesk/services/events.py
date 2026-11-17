from __future__ import annotations

from typing import Any

from ..db import session_scope
from ..models import SessionEvent
from ..security import redact
from ..ws import hub


async def emit(project_id: int, session_id: int | None, message: str, *, kind: str = "log", level: str = "info",
               ws_type: str = "log", extra: dict[str, Any] | None = None) -> None:
    """Persist an activity event and push it to live subscribers."""
    message = redact(message)[:8000]
    with session_scope() as db:
        ev = SessionEvent(project_id=project_id, session_id=session_id, kind=kind, level=level, message=message)
        db.add(ev)
        db.flush()
        payload = {"id": ev.id, "at": ev.at.isoformat(), "session_id": session_id, "kind": kind, "level": level,
                   "message": message, **(extra or {})}
    await hub.publish(project_id, ws_type, payload)


async def push(project_id: int, type_: str, data: dict[str, Any] | None = None) -> None:
    await hub.publish(project_id, type_, data or {})
