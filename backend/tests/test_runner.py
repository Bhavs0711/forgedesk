"""Orchestration tests. ScriptedBackend stands in for the LLM only; DB, scheduler, tests and git are real."""
import asyncio

import pytest
from sqlalchemy import select

from forgedesk.agent.backend import RunResult
from forgedesk.agent.runner import ProjectRunner, RunnerError, recover_after_crash
from forgedesk.db import session_scope
from forgedesk.models import AgentSession, Feature, FeatureStatus, Project, SessionStatus, TestRun


class ScriptedBackend:
    requires_api_key = False

    def __init__(self, script):
        self.script, self.calls = script, 0

    async def run(self, ctx, *, tools, **kw):
        self.calls += 1
        await ctx.checkpoint()
        await self.script(ctx, {t.name: t.handler for t in tools}, self.calls)
        return RunResult(turns=3, cost_usd=0.01)


def setup_project(root, n=1, test_command="exit 0"):
    path = root / "proj"
    path.mkdir()
    with session_scope() as db:
        p = Project(name="proj", path=str(path), test_command=test_command, initialized=True)
        db.add(p)
        db.flush()
        for i in range(n):
            db.add(Feature(project_id=p.id, title=f"f{i}", sequence=i))
        return p.id


async def finished(runner, timeout=5):
    await asyncio.wait_for(asyncio.shield(runner.task), timeout)


async def happy(ctx, tools, _n):
    await tools["run_tests"]({})
    await tools["feature_complete"]({"summary": "done"})


async def test_completes_features_with_real_test_runs(env):
    pid = setup_project(env, n=2)
    r = ProjectRunner(pid, lambda: ScriptedBackend(happy))
    r.start()
    await finished(r)
    with session_scope() as db:
        assert {f.status for f in db.scalars(select(Feature))} == {FeatureStatus.completed}
        runs = list(db.scalars(select(TestRun)))
        assert all(t.exit_code == 0 for t in runs) and {t.kind for t in runs} == {"feature", "regression"}
        sessions = list(db.scalars(select(AgentSession)))
        assert all(s.status == SessionStatus.completed for s in sessions) and sessions[0].turns == 3


async def test_cannot_complete_without_passing_tests(env):
    pid = setup_project(env, test_command="exit 1")

    async def liar(ctx, tools, _n):
        res = await tools["feature_complete"]({"summary": "trust me"})
        assert res.get("is_error")
        await tools["run_tests"]({})
        res = await tools["feature_complete"]({"summary": "still trust me"})
        assert res.get("is_error")

    r = ProjectRunner(pid, lambda: ScriptedBackend(liar))
    r.start()
    await finished(r)
    with session_scope() as db:
        f = db.scalars(select(Feature)).one()
        assert f.status == FeatureStatus.failed and f.attempts == 3  # retried, then gave up honestly
    assert r.failures == 3


async def test_backoff_is_used_between_failures(env):
    pid = setup_project(env)
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    async def fail(ctx, tools, _n):
        await tools["feature_fail"]({"reason": "nope"})

    r = ProjectRunner(pid, lambda: ScriptedBackend(fail), sleep=fake_sleep)
    r.start()
    await finished(r)
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 1.2  # exponential growth despite jitter


async def test_one_runner_per_project(env):
    pid = setup_project(env)
    gate = asyncio.Event()

    async def slow(ctx, tools, _n):
        await gate.wait()
        await happy(ctx, tools, _n)

    r = ProjectRunner(pid, lambda: ScriptedBackend(slow))
    r.start()
    with pytest.raises(RunnerError):
        r.start()
    gate.set()
    await finished(r)


async def test_db_rejects_second_live_session(env):
    pid = setup_project(env)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError), session_scope() as db:
        db.add_all([AgentSession(project_id=pid), AgentSession(project_id=pid)])


async def test_pause_resume_and_stop_releases_claim(env):
    pid = setup_project(env, n=2)
    entered = asyncio.Event()

    async def blocking(ctx, tools, _n):
        entered.set()
        await asyncio.sleep(30)

    r = ProjectRunner(pid, lambda: ScriptedBackend(blocking))
    r.start()
    await asyncio.wait_for(entered.wait(), 3)
    await r.pause()
    assert r.snapshot()["state"] == "paused"
    with session_scope() as db:
        assert db.scalars(select(AgentSession)).one().status == SessionStatus.paused
    await r.resume()
    await r.stop()
    assert r.snapshot()["state"] == "idle"
    with session_scope() as db:
        assert {f.status for f in db.scalars(select(Feature))} == {FeatureStatus.pending}
        assert db.scalars(select(AgentSession)).one().status == SessionStatus.stopped


async def test_crash_recovery(env):
    pid = setup_project(env)
    with session_scope() as db:
        s = AgentSession(project_id=pid, status=SessionStatus.running, sdk_session_id="abc")
        db.add(s)
        db.flush()
        f = db.scalars(select(Feature)).one()
        s.feature_id = f.id
        f.status, f.claimed_by_session = FeatureStatus.in_progress, s.id
    assert recover_after_crash() == {"sessions_interrupted": 1, "features_released": 1, "approvals_expired": 0}
    with session_scope() as db:
        assert db.scalars(select(Feature)).one().status == FeatureStatus.pending
        assert db.scalars(select(AgentSession)).one().status == SessionStatus.interrupted
    # the next run resumes the interrupted SDK session
    seen = {}

    class Spy(ScriptedBackend):
        async def run(self, ctx, **kw):
            seen["resume"] = kw["resume"]
            return await super().run(ctx, **kw)

    r = ProjectRunner(pid, lambda: Spy(happy))
    r.start()
    await finished(r)
    assert seen["resume"] == "abc"


async def test_missing_api_key_refused(env, monkeypatch):
    from forgedesk.agent.backend import ClaudeSdkBackend
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    pid = setup_project(env)
    with pytest.raises(RunnerError, match="ANTHROPIC_API_KEY"):
        ProjectRunner(pid, ClaudeSdkBackend).start()


async def test_initializer_creates_plan(env):
    path = env / "np"
    path.mkdir()
    with session_scope() as db:
        p = Project(name="np", path=str(path), specification="a todo app", test_command="exit 0")
        db.add(p)
        db.flush()
        pid = p.id

    async def planner(ctx, tools, n):
        if "submit_feature_plan" in tools:
            await tools["submit_feature_plan"]({"features": [
                {"title": "Data model", "description": "x", "acceptance_criteria": ["a"]},
                {"title": "API", "description": "y", "acceptance_criteria": ["b"], "depends_on": [1]}]})
        else:
            await happy(ctx, tools, n)

    r = ProjectRunner(pid, lambda: ScriptedBackend(planner))
    r.start()
    await finished(r)
    with session_scope() as db:
        assert db.get(Project, pid).initialized
        titles = [f.title for f in db.scalars(select(Feature).order_by(Feature.sequence))]
        assert titles == ["Data model", "API"]
        assert {s.kind for s in db.scalars(select(AgentSession))} == {"initializer", "coding"}
