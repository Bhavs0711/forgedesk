"""Run a project's test command, on the host or in Docker, and persist the real result."""
from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

from ..config import get_settings
from ..db import session_scope
from ..models import TestRun
from ..security import Verdict, classify_command, redact

TAIL_CHARS = 6000


def docker_available() -> bool:
    return shutil.which("docker") is not None


async def run_command(command: str, cwd: Path, timeout: float = 600) -> tuple[int, str, float, bool]:
    """Returns (exit_code, output, seconds, ran_in_docker)."""
    s = get_settings()
    in_docker = s.use_docker and docker_available()
    if in_docker:
        argv = ["docker", "run", "--rm", "--network", "none", "-v", f"{cwd}:/work", "-w", "/work", s.docker_image,
                "sh", "-c", command]
    else:
        argv = ["sh", "-c", command]
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(*argv, cwd=cwd, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT, start_new_session=True)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        code = proc.returncode or 0
    except TimeoutError:
        proc.kill()
        out, _ = await proc.communicate()
        out += f"\n[timed out after {timeout:.0f}s]".encode()
        code = 124
    return code, redact(out.decode(errors="replace")), time.monotonic() - started, in_docker


async def run_project_tests(project_id: int, path: Path, command: str, *, feature_id: int | None = None,
                            session_id: int | None = None, kind: str = "feature") -> TestRun:
    if not command.strip():
        raise ValueError("no test command configured for this project")
    if classify_command(command, path).verdict == Verdict.deny:
        raise ValueError("test command rejected by security policy")
    code, out, secs, _ = await run_command(command, path)
    with session_scope() as db:
        run = TestRun(project_id=project_id, feature_id=feature_id, session_id=session_id, kind=kind, command=command,
                      exit_code=code, duration_seconds=round(secs, 2), output_tail=out[-TAIL_CHARS:])
        db.add(run)
        db.flush()
        return run
