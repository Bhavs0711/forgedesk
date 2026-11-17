"""MCP tools exposed to the coding agent. Completion is gated on a real, passing test run."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, tool
from sqlalchemy import select

from ..db import session_scope
from ..models import TestRun
from ..services import features as feat
from ..services.events import emit, push
from ..services.testing import run_project_tests


@dataclass
class SessionContext:
    project_id: int
    session_id: int
    project_path: Path
    test_command: str
    feature_id: int | None = None
    checkpoint: Callable[[], Awaitable[None]] = field(default=lambda: _noop())  # type: ignore[assignment]
    on_sdk_session: Callable[[str], None] = field(default=lambda _sid: None)
    outcome: str | None = None  # "completed" | "failed"
    reason: str = ""
    plan_created: int = 0


async def _noop() -> None:
    return None


def _text(msg: str, error: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"content": [{"type": "text", "text": msg}]}
    if error:
        out["is_error"] = True
    return out


def coding_tools(ctx: SessionContext) -> list[SdkMcpTool]:
    @tool("run_tests", "Run the project's test command and return the real result.", {"type": "object", "properties": {}})
    async def run_tests(_args: dict[str, Any]) -> dict[str, Any]:
        if not ctx.test_command:
            return _text("No test command is configured for this project.", error=True)
        run = await run_project_tests(ctx.project_id, ctx.project_path, ctx.test_command,
                                      feature_id=ctx.feature_id, session_id=ctx.session_id)
        verdict = "PASSED" if run.exit_code == 0 else f"FAILED (exit {run.exit_code})"
        await emit(ctx.project_id, ctx.session_id, f"Tests {verdict} in {run.duration_seconds}s", kind="test",
                   level="info" if run.exit_code == 0 else "warn", ws_type="test_result",
                   extra={"run_id": run.id, "exit_code": run.exit_code, "feature_id": ctx.feature_id})
        return _text(f"Tests {verdict}\n{run.output_tail[-3000:]}", error=run.exit_code != 0)

    @tool("feature_complete", "Mark the current feature complete. Requires a passing run_tests in this session.",
          {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]})
    async def feature_complete(args: dict[str, Any]) -> dict[str, Any]:
        if ctx.test_command:
            with session_scope() as db:
                last = db.scalars(select(TestRun).where(TestRun.session_id == ctx.session_id)
                                  .order_by(TestRun.id.desc())).first()
            if last is None or last.exit_code != 0:
                return _text("Rejected: the most recent run_tests in this session has not passed.", error=True)
        ctx.outcome, ctx.reason = "completed", str(args.get("summary", ""))
        return _text("Recorded. Finish your turn.")

    @tool("feature_fail", "Report that the current feature cannot be completed, with the real reason.",
          {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]})
    async def feature_fail(args: dict[str, Any]) -> dict[str, Any]:
        ctx.outcome, ctx.reason = "failed", str(args.get("reason", "unspecified"))
        return _text("Recorded. Finish your turn.")

    return [run_tests, feature_complete, feature_fail]


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"features": {"type": "array", "minItems": 1, "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "description": {"type": "string"},
                       "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                       "priority": {"type": "integer"},
                       "depends_on": {"type": "array", "items": {"type": "integer"}}},
        "required": ["title", "description", "acceptance_criteria"]}}},
    "required": ["features"],
}


def initializer_tools(ctx: SessionContext) -> list[SdkMcpTool]:
    @tool("submit_feature_plan", "Submit the complete feature plan. Call once.", PLAN_SCHEMA)
    async def submit_feature_plan(args: dict[str, Any]) -> dict[str, Any]:
        plan = args.get("features") or []
        with session_scope() as db:
            created = feat.create_from_plan(db, ctx.project_id, plan)
        ctx.plan_created = len(created)
        if not created:
            return _text("No new features were created (empty or duplicate plan).", error=True)
        ctx.outcome = "completed"
        await push(ctx.project_id, "features_changed")
        return _text(f"Stored {len(created)} features. Finish your turn.")

    return [submit_feature_plan]
