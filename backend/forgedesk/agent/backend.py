"""Claude Agent SDK integration. API-key authentication only."""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SdkMcpTool,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
)

from ..security import PathNotAllowed, Verdict, classify_command, resolve_within
from .approvals import broker
from .tools import SessionContext

EventSink = Callable[[str, str], Awaitable[None]]  # (kind, text)
FILE_TOOLS = {"Read": "file_path", "Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path", "Glob": "path", "Grep": "path"}


class AuthError(RuntimeError):
    pass


@dataclass
class RunResult:
    turns: int = 0
    cost_usd: float = 0.0
    is_error: bool = False
    error: str = ""


class AgentBackend(Protocol):
    requires_api_key: bool

    async def run(self, ctx: SessionContext, *, system_prompt: str, prompt: str, tools: list[SdkMcpTool],
                  model: str, max_turns: int, resume: str | None, emit: EventSink) -> RunResult: ...


def make_permission_callback(ctx: SessionContext):
    async def can_use_tool(tool_name: str, tool_input: dict[str, Any], _context: Any):
        if tool_name.startswith("mcp__forge__"):
            return PermissionResultAllow()
        if tool_name in FILE_TOOLS:
            raw = tool_input.get(FILE_TOOLS[tool_name])
            if raw is None and tool_name in ("Glob", "Grep"):
                return PermissionResultAllow()  # defaults to cwd, which is the project directory
            try:
                resolve_within(ctx.project_path, str(raw))
            except PathNotAllowed as e:
                return PermissionResultDeny(message=f"Denied: {e}")
            return PermissionResultAllow()
        if tool_name == "Bash":
            cmd = str(tool_input.get("command", ""))
            d = classify_command(cmd, ctx.project_path)
            if d.verdict == Verdict.allow:
                return PermissionResultAllow()
            if d.verdict == Verdict.deny:
                return PermissionResultDeny(message=f"Denied by policy: {d.reason}")
            ok = await broker.request(ctx.project_id, ctx.session_id, cmd, d.reason)
            return PermissionResultAllow() if ok else PermissionResultDeny(message="A human declined or did not answer this command.")
        return PermissionResultDeny(message=f"Tool {tool_name} is not enabled.")

    return can_use_tool


def _summarize(block: ToolUseBlock) -> str:
    inp = block.input or {}
    detail = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("path") or ""
    return f"{block.name} {str(detail)[:300]}".strip()


class ClaudeSdkBackend:
    requires_api_key = True

    async def run(self, ctx: SessionContext, *, system_prompt: str, prompt: str, tools: list[SdkMcpTool],
                  model: str, max_turns: int, resume: str | None, emit: EventSink) -> RunResult:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AuthError("ANTHROPIC_API_KEY is not set. ForgeDesk uses Anthropic API-key authentication only.")
        options = ClaudeAgentOptions(
            system_prompt=system_prompt, model=model, cwd=str(ctx.project_path), max_turns=max_turns, resume=resume,
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
            mcp_servers={"forge": create_sdk_mcp_server("forge", tools=tools)},
            permission_mode="default", can_use_tool=make_permission_callback(ctx), setting_sources=[],
            env={"ANTHROPIC_API_KEY": key},
        )
        result = RunResult()
        async with ClaudeSDKClient(options) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                await ctx.checkpoint()  # honours pause/stop between messages
                sid = getattr(msg, "session_id", None)
                if sid:
                    ctx.on_sdk_session(sid)
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            await emit("assistant", block.text.strip())
                        elif isinstance(block, ToolUseBlock):
                            await emit("tool", _summarize(block))
                elif isinstance(msg, ResultMessage):
                    result.turns = msg.num_turns
                    result.cost_usd = msg.total_cost_usd or 0.0
                    result.is_error = bool(msg.is_error)
                    if msg.is_error:
                        result.error = str(msg.result or msg.subtype)
        return result
