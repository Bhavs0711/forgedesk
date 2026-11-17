"""Human approval gate for risky commands. Pending requests live in memory (futures) and the DB (audit)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ..config import get_settings
from ..db import session_scope
from ..models import Approval, ApprovalStatus
from ..services.events import emit, push


class ApprovalBroker:
    def __init__(self) -> None:
        self._waiters: dict[int, asyncio.Future[bool]] = {}
        self._project_for: dict[int, int] = {}

    async def request(self, project_id: int, session_id: int | None, command: str, reason: str) -> bool:
        with session_scope() as db:
            a = Approval(project_id=project_id, session_id=session_id, command=command[:4000], reason=reason[:300])
            db.add(a)
            db.flush()
            aid = a.id
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._waiters[aid] = fut
        self._project_for[aid] = project_id
        await emit(project_id, session_id, f"Approval needed ({reason}): {command}", kind="approval", level="warn",
                   ws_type="approval_requested", extra={"approval_id": aid, "command": command, "reason": reason})
        try:
            approved = await asyncio.wait_for(fut, timeout=get_settings().approval_timeout_seconds)
            status = ApprovalStatus.approved if approved else ApprovalStatus.denied
        except TimeoutError:
            approved, status = False, ApprovalStatus.expired
        finally:
            self._waiters.pop(aid, None)
            self._project_for.pop(aid, None)
        with session_scope() as db:
            a = db.get(Approval, aid)
            if a:
                a.status, a.decided_at = status, datetime.now(UTC)
        await push(project_id, "approval_resolved", {"approval_id": aid, "status": status.value})
        return approved

    def decide(self, approval_id: int, approve: bool) -> bool:
        fut = self._waiters.get(approval_id)
        if not fut or fut.done():
            return False
        fut.set_result(approve)
        return True

    def deny_all(self, project_id: int | None = None) -> None:
        """Deny pending approvals. If project_id is given, only deny that project's approvals."""
        for aid, fut in self._waiters.items():
            if project_id is not None and self._project_for.get(aid) != project_id:
                continue
            if not fut.done():
                fut.set_result(False)


broker = ApprovalBroker()
