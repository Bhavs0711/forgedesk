import asyncio

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, create_sdk_mcp_server

from forgedesk.agent.approvals import broker
from forgedesk.agent.backend import make_permission_callback
from forgedesk.agent.tools import SessionContext, coding_tools
from forgedesk.db import session_scope
from forgedesk.models import AgentSession, Approval, ApprovalStatus, Project


@pytest.fixture
def ctx(env):
    (env / "p").mkdir()
    with session_scope() as db:
        p = Project(name="p", path=str(env / "p"))
        db.add(p)
        db.flush()
        sess = AgentSession(project_id=p.id)
        db.add(sess)
        db.flush()
        pid, sid = p.id, sess.id
    return SessionContext(project_id=pid, session_id=sid, project_path=(env / "p").resolve(), test_command="")


async def test_file_tools_confined(ctx):
    cb = make_permission_callback(ctx)
    assert isinstance(await cb("Read", {"file_path": "src/a.py"}, None), PermissionResultAllow)
    assert isinstance(await cb("Write", {"file_path": "/etc/passwd"}, None), PermissionResultDeny)
    assert isinstance(await cb("Edit", {"file_path": "../../x"}, None), PermissionResultDeny)
    assert isinstance(await cb("WebFetch", {"url": "http://x"}, None), PermissionResultDeny)
    assert isinstance(await cb("mcp__forge__run_tests", {}, None), PermissionResultAllow)


async def test_bash_policy_and_approval_flow(ctx):
    cb = make_permission_callback(ctx)
    assert isinstance(await cb("Bash", {"command": "pytest"}, None), PermissionResultAllow)
    assert isinstance(await cb("Bash", {"command": "sudo ls"}, None), PermissionResultDeny)

    task = asyncio.create_task(cb("Bash", {"command": "rm -rf build"}, None))
    for _ in range(50):
        await asyncio.sleep(0.02)
        if broker._waiters:
            break
    (aid,) = broker._waiters
    assert broker.decide(aid, False)
    assert isinstance(await task, PermissionResultDeny)
    with session_scope() as db:
        assert db.get(Approval, aid).status == ApprovalStatus.denied

    task = asyncio.create_task(cb("Bash", {"command": "rm -rf build"}, None))
    await asyncio.sleep(0.1)
    (aid,) = broker._waiters
    broker.decide(aid, True)
    assert isinstance(await task, PermissionResultAllow)


def test_sdk_tool_server_builds(ctx):
    tools = coding_tools(ctx)
    assert {t.name for t in tools} == {"run_tests", "feature_complete", "feature_fail"}
    assert create_sdk_mcp_server("forge", tools=tools)["type"] == "sdk"


async def test_deny_all_filters_by_project(ctx, env):
    """broker.deny_all(project_id) only denies that project's approvals, not other projects'."""
    import asyncio

    from forgedesk.db import session_scope
    from forgedesk.models import AgentSession, Project

    # Set up a second project + session
    (env / "q").mkdir()
    with session_scope() as db:
        q = Project(name="q", path=str(env / "q"))
        db.add(q)
        db.flush()
        sess = AgentSession(project_id=q.id)
        db.add(sess)
        db.flush()
        qpid, qsid = q.id, sess.id

    cb = make_permission_callback(ctx)
    cb2 = make_permission_callback(SessionContext(project_id=qpid, session_id=qsid,
                                                   project_path=(env / "q").resolve(), test_command=""))

    # Start two approval requests on different projects
    task_a = asyncio.create_task(cb("Bash", {"command": "rm -rf build"}, None))
    task_b = asyncio.create_task(cb2("Bash", {"command": "rm -rf build"}, None))
    for _ in range(50):
        await asyncio.sleep(0.02)
        if len(broker._waiters) >= 2:
            break

    # Deny only ctx's project
    broker.deny_all(ctx.project_id)
    result_a = await asyncio.wait_for(task_a, 2)
    assert isinstance(result_a, PermissionResultDeny)

    # The other project's approval should still be pending
    assert not task_b.done()
    # Clean up: deny the other one too
    broker.deny_all(qpid)
    result_b = await asyncio.wait_for(task_b, 2)
    assert isinstance(result_b, PermissionResultDeny)


async def test_approval_timeout_fails_safely(ctx, monkeypatch):
    """When no human responds, the approval times out to 'denied' and the command is blocked."""

    from forgedesk.config import get_settings

    monkeypatch.setenv("FORGEDESK_APPROVAL_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()

    cb = make_permission_callback(ctx)
    result = await cb("Bash", {"command": "rm -rf build"}, None)
    assert isinstance(result, PermissionResultDeny)

    get_settings.cache_clear()
