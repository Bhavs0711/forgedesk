"""Per-project agent orchestration: scheduling, pause/resume/stop, limits, backoff, crash recovery."""
from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..config import anthropic_api_key_configured
from ..db import session_scope
from ..models import AgentSession, Approval, ApprovalStatus, Feature, FeatureStatus, Project, SessionStatus
from ..security import redact
from ..services import features as feat
from ..services import git, runtime_settings
from ..services.backoff import delay
from ..services.events import emit, push
from ..services.projects import project_path
from ..services.testing import run_project_tests
from .approvals import broker
from .backend import AgentBackend, ClaudeSdkBackend
from .prompts import CODING_SYSTEM, INITIALIZER_SYSTEM, coding_prompt
from .tools import SessionContext, coding_tools, initializer_tools

BackendFactory = Callable[[], AgentBackend]
MAX_ATTEMPTS_PER_FEATURE = 3


class RunnerError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectRunner:
    def __init__(self, project_id: int, backend_factory: BackendFactory, sleep: Callable[[float], asyncio.Future] | None = None):
        self.project_id = project_id
        self._backend_factory = backend_factory
        self._sleep = sleep or asyncio.sleep
        self._gate = asyncio.Event()
        self._gate.set()
        self._stopping = False
        self.task: asyncio.Task[None] | None = None
        self.state = "idle"  # idle | running | paused | stopping
        self.session_id: int | None = None
        self.feature_id: int | None = None
        self.failures = 0

    # ---- controls -------------------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self) -> None:
        if self.active:
            raise RunnerError("an agent is already running for this project")
        backend = self._backend_factory()
        if backend.requires_api_key and not anthropic_api_key_configured():
            raise RunnerError("ANTHROPIC_API_KEY is not configured on the server")
        self._stopping = False
        self._gate.set()
        self.failures = 0
        self.state = "running"
        self.task = asyncio.create_task(self._main(backend), name=f"forgedesk-agent-{self.project_id}")

    async def pause(self) -> None:
        if self.state != "running":
            raise RunnerError("agent is not running")
        self._gate.clear()
        self.state = "paused"
        self._set_session_status(SessionStatus.paused)
        await emit(self.project_id, self.session_id, "Paused. The current tool call finishes first.", kind="status")
        await push(self.project_id, "agent_status", self.snapshot())

    async def resume(self) -> None:
        if self.state != "paused":
            raise RunnerError("agent is not paused")
        self.state = "running"
        self._set_session_status(SessionStatus.running)
        self._gate.set()
        await emit(self.project_id, self.session_id, "Resumed.", kind="status")
        await push(self.project_id, "agent_status", self.snapshot())

    async def stop(self) -> None:
        if not self.active:
            raise RunnerError("agent is not running")
        self._stopping = True
        self.state = "stopping"
        self._gate.set()
        broker.deny_all(self.project_id)
        assert self.task is not None
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self.task

    def snapshot(self) -> dict:
        return {"state": self.state if self.active else "idle", "session_id": self.session_id,
                "feature_id": self.feature_id, "consecutive_failures": self.failures}

    async def _checkpoint(self) -> None:
        await self._gate.wait()
        if self._stopping:
            raise asyncio.CancelledError

    def _set_session_status(self, status: SessionStatus) -> None:
        if self.session_id is None:
            return
        with session_scope() as db:
            s = db.get(AgentSession, self.session_id)
            if s and s.status in (SessionStatus.running, SessionStatus.paused):
                s.status = status

    # ---- main loop ------------------------------------------------------------------------------
    async def _main(self, backend: AgentBackend) -> None:
        final = "idle"
        try:
            await emit(self.project_id, None, "Agent started.", kind="status")
            await push(self.project_id, "agent_status", self.snapshot())
            with session_scope() as db:
                has_features = db.scalar(select(Feature.id).where(Feature.project_id == self.project_id).limit(1)) is not None
            if not has_features and not await self._initialize(backend):
                return
            await self._work_loop(backend)
            final = "finished"
        except asyncio.CancelledError:
            await emit(self.project_id, self.session_id, "Agent stopped by user.", kind="status", level="warn")
        except Exception as e:  # unexpected orchestration failure
            await emit(self.project_id, self.session_id, f"Agent crashed: {redact(str(e))}", kind="status", level="error")
        finally:
            self.state, self.feature_id = "idle", None
            await push(self.project_id, "agent_status", {**self.snapshot(), "final": final})
            await push(self.project_id, "progress", self._progress())

    def _progress(self) -> dict:
        with session_scope() as db:
            return feat.progress(db, self.project_id)

    def _open_session(self, kind: str) -> tuple[int, Project]:
        with session_scope() as db:
            project = db.get(Project, self.project_id)
            if project is None:
                raise RunnerError("project no longer exists")
            s = AgentSession(project_id=self.project_id, kind=kind)
            db.add(s)
            try:
                db.flush()
            except IntegrityError as e:
                raise RunnerError("another live session exists for this project") from e
            db.expunge(project)
            return s.id, project

    def _close_session(self, status: SessionStatus, error: str = "", turns: int = 0, cost: float = 0.0) -> None:
        if self.session_id is None:
            return
        with session_scope() as db:
            s = db.get(AgentSession, self.session_id)
            if s:
                s.status, s.ended_at, s.error = status, _now(), redact(error)[:2000]
                s.turns, s.cost_usd = turns, cost

    async def _initialize(self, backend: AgentBackend) -> bool:
        sid, project = self._open_session("initializer")
        self.session_id = sid
        if not project.specification.strip():
            self._close_session(SessionStatus.failed, "project has no specification")
            await emit(self.project_id, sid, "Cannot initialize: the project specification is empty.", level="error", kind="status")
            return False
        ctx = SessionContext(project_id=self.project_id, session_id=sid, project_path=project_path(project),
                             test_command=project.test_command, checkpoint=self._checkpoint)
        await emit(self.project_id, sid, "Analysing the specification and planning features.", kind="status")
        try:
            async with asyncio.timeout(15 * 60):
                with session_scope() as db:
                    model = runtime_settings.load(db).model
                res = await backend.run(ctx, system_prompt=INITIALIZER_SYSTEM, tools=initializer_tools(ctx), model=model,
                                        prompt=f"Project: {project.name}\n\nSpecification:\n{project.specification}",
                                        max_turns=30, resume=None, emit=self._sink(sid))
        except asyncio.CancelledError:
            self._close_session(SessionStatus.stopped)
            raise
        except Exception as e:
            self._close_session(SessionStatus.failed, str(e))
            await emit(self.project_id, sid, f"Initialization failed: {redact(str(e))}", level="error", kind="status")
            return False
        ok = ctx.outcome == "completed" and ctx.plan_created > 0
        self._close_session(SessionStatus.completed if ok else SessionStatus.failed,
                            "" if ok else (res.error or "agent did not submit a feature plan"), res.turns, res.cost_usd)
        if ok:
            with session_scope() as db:
                db.get(Project, self.project_id).initialized = True  # type: ignore[union-attr]
            await emit(self.project_id, sid, f"Created {ctx.plan_created} features.", kind="status")
            await push(self.project_id, "features_changed")
        else:
            await emit(self.project_id, sid, "Initialization produced no features.", level="error", kind="status")
        return ok

    def _sink(self, session_id: int):
        async def sink(kind: str, text: str) -> None:
            await emit(self.project_id, session_id, text, kind=kind)
        return sink

    async def _work_loop(self, backend: AgentBackend) -> None:
        while True:
            await self._checkpoint()
            with session_scope() as db:
                limits = runtime_settings.load(db)
                candidates = feat.eligible(db, self.project_id)
                has_candidates = any(f.attempts < MAX_ATTEMPTS_PER_FEATURE for f in candidates)
                counts = feat.progress(db, self.project_id)
            if not has_candidates:
                note = (f"No eligible features remain ({counts['completed']}/{counts['total']} completed, "
                        f"{counts['failed']} failed, {counts['blocked']} blocked).")
                await emit(self.project_id, None, note, kind="status")
                await self._final_regression()
                return
            outcome = await self._run_one_feature(backend, limits)
            if outcome == "failed":
                self.failures += 1
                if self.failures >= limits.max_consecutive_failures:
                    await emit(self.project_id, self.session_id,
                               f"Stopping: {self.failures} consecutive failures.", kind="status", level="error")
                    return
                wait = delay(self.failures, *self._backoff_params())
                await emit(self.project_id, self.session_id, f"Backing off {wait:.0f}s before the next attempt.", kind="status", level="warn")
                await self._interruptible_sleep(wait)
            elif outcome == "completed":
                self.failures = 0

    def _backoff_params(self) -> tuple[float, float]:
        from ..config import get_settings
        s = get_settings()
        return s.backoff_base_seconds, s.backoff_max_seconds

    async def _interruptible_sleep(self, seconds: float) -> None:
        await self._sleep(seconds)
        await self._checkpoint()

    async def _run_one_feature(self, backend: AgentBackend, limits: runtime_settings.Limits) -> str:
        """Returns 'completed', 'failed' or 'skipped'."""
        sid, project = self._open_session("coding")
        self.session_id = sid
        resume_id: str | None = None
        with session_scope() as db:
            feature = feat.claim_next(db, self.project_id, sid, MAX_ATTEMPTS_PER_FEATURE)
            if feature is None:
                db.get(AgentSession, sid).status = SessionStatus.completed  # type: ignore[union-attr]
                db.get(AgentSession, sid).ended_at = _now()  # type: ignore[union-attr]
                return "skipped"
            fid, title = feature.id, feature.title
            db.get(AgentSession, sid).feature_id = fid  # type: ignore[union-attr]
            prompt = coding_prompt(feature.title, feature.description, list(feature.acceptance_criteria or []),
                                   feature.failure_reason, project.test_command)
            prev = db.scalars(select(AgentSession).where(AgentSession.feature_id == fid, AgentSession.id != sid,
                                                         AgentSession.status == SessionStatus.interrupted,
                                                         AgentSession.sdk_session_id.is_not(None))
                              .order_by(AgentSession.id.desc())).first()
            resume_id = prev.sdk_session_id if prev else None
        self.feature_id = fid
        await push(self.project_id, "agent_status", self.snapshot())
        await push(self.project_id, "features_changed")
        await emit(self.project_id, sid, f"Working on: {title}", kind="feature")

        def remember_sdk_session(value: str) -> None:
            with session_scope() as db:
                s = db.get(AgentSession, sid)
                if s and s.sdk_session_id != value:
                    s.sdk_session_id = value

        ctx = SessionContext(project_id=self.project_id, session_id=sid, project_path=project_path(project),
                             test_command=project.test_command, feature_id=fid, checkpoint=self._checkpoint,
                             on_sdk_session=remember_sdk_session)
        started = time.monotonic()
        error, turns, cost = "", 0, 0.0
        try:
            async with asyncio.timeout(limits.max_session_minutes * 60):
                res = await backend.run(ctx, system_prompt=CODING_SYSTEM, prompt=prompt, tools=coding_tools(ctx),
                                        model=limits.model, max_turns=limits.max_turns_per_session,
                                        resume=resume_id, emit=self._sink(sid))
            turns, cost = res.turns, res.cost_usd
            if res.is_error:
                error = res.error
        except asyncio.CancelledError:
            with session_scope() as db:
                feat.release_claims(db, sid)
                db.get(Feature, fid).seconds_spent += time.monotonic() - started  # type: ignore[union-attr]
            self._close_session(SessionStatus.stopped)
            raise
        except TimeoutError:
            error = f"session exceeded the {limits.max_session_minutes} minute limit"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        elapsed = time.monotonic() - started

        if ctx.outcome == "completed" and not error:
            with session_scope() as db:
                feat.finish(db, fid, FeatureStatus.completed, seconds=elapsed)
            self._close_session(SessionStatus.completed, "", turns, cost)
            await emit(self.project_id, sid, f"Completed: {title}. {ctx.reason}", kind="feature")
            if limits.auto_commit:
                head = await git.commit_all(project_path(project), f"feat: {title}\n\nImplemented by ForgeDesk agent session {sid}.")
                if head:
                    await emit(self.project_id, sid, f"Committed {head}.", kind="git")
            await push(self.project_id, "features_changed")
            await push(self.project_id, "progress", self._progress())
            return "completed"

        reason = redact(error or ctx.reason or "agent ended without completing the feature")[:1000]
        with session_scope() as db:
            f = db.get(Feature, fid)
            assert f is not None
            exhausted = f.attempts >= MAX_ATTEMPTS_PER_FEATURE
            if exhausted:
                feat.finish(db, fid, FeatureStatus.failed, reason=reason, seconds=elapsed)
            else:
                f.status, f.claimed_by_session, f.failure_reason = FeatureStatus.pending, None, reason
                f.seconds_spent += elapsed
        self._close_session(SessionStatus.failed, reason, turns, cost)
        await emit(self.project_id, sid, f"Failed: {title}: {reason}", kind="feature", level="error")
        await push(self.project_id, "features_changed")
        return "failed"

    async def _final_regression(self) -> None:
        with session_scope() as db:
            p = db.get(Project, self.project_id)
            if not p or not p.test_command:
                return
            path, cmd = project_path(p), p.test_command
        try:
            run = await run_project_tests(self.project_id, path, cmd, kind="regression")
        except ValueError as e:
            await emit(self.project_id, None, f"Regression run skipped: {e}", level="warn", kind="test")
            return
        await emit(self.project_id, None, f"Regression suite {'PASSED' if run.exit_code == 0 else 'FAILED'}",
                   kind="test", level="info" if run.exit_code == 0 else "error", ws_type="test_result",
                   extra={"run_id": run.id, "exit_code": run.exit_code})


class AgentManager:
    def __init__(self, backend_factory: BackendFactory = ClaudeSdkBackend) -> None:
        self.backend_factory = backend_factory
        self.runners: dict[int, ProjectRunner] = {}

    def runner(self, project_id: int) -> ProjectRunner:
        r = self.runners.get(project_id)
        if r is None:
            r = self.runners[project_id] = ProjectRunner(project_id, self.backend_factory)
        return r

    def status(self, project_id: int) -> dict:
        return self.runner(project_id).snapshot()

    async def shutdown(self) -> None:
        for r in self.runners.values():
            if r.active:
                with contextlib.suppress(Exception):
                    await r.stop()


def recover_after_crash() -> dict[str, int]:
    """Run once at startup. Anything marked live belonged to a process that no longer exists."""
    with session_scope() as db:
        live = list(db.scalars(select(AgentSession).where(AgentSession.status.in_([SessionStatus.running, SessionStatus.paused]))))
        released = 0
        for s in live:
            s.status, s.ended_at, s.error = SessionStatus.interrupted, _now(), "server stopped while this session was live"
            released += feat.release_claims(db, s.id)
        stale = db.execute(update(Approval).where(Approval.status == ApprovalStatus.pending)
                           .values(status=ApprovalStatus.expired, decided_at=_now()))
        return {"sessions_interrupted": len(live), "features_released": released, "approvals_expired": stale.rowcount or 0}
