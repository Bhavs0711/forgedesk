from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

AUTHOR = ["-c", "user.name=ForgeDesk Agent", "-c", "user.email=agent@forgedesk.local"]


async def _git(path: Path, *args: str) -> tuple[int, str]:
    if not shutil.which("git"):
        return 127, "git is not installed"
    proc = await asyncio.create_subprocess_exec("git", *AUTHOR, *args, cwd=path,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace").strip()


async def is_repo(path: Path) -> bool:
    code, _ = await _git(path, "rev-parse", "--is-inside-work-tree")
    return code == 0


async def ensure_repo(path: Path) -> None:
    if not await is_repo(path):
        await _git(path, "init", "-q")


async def commit_all(path: Path, message: str) -> str | None:
    """Commit working-tree changes. Returns the short hash, or None if there was nothing to commit."""
    await _git(path, "add", "-A")
    code, _ = await _git(path, "diff", "--cached", "--quiet")
    if code == 0:
        return None
    code, _ = await _git(path, "commit", "-q", "-m", message)
    if code != 0:
        return None
    _, head = await _git(path, "rev-parse", "--short", "HEAD")
    return head


async def log(path: Path, limit: int = 30) -> list[dict[str, str]]:
    code, out = await _git(path, "log", f"-{limit}", "--pretty=format:%h%x1f%an%x1f%aI%x1f%s")
    if code != 0 or not out:
        return []
    rows = [line.split("\x1f") for line in out.splitlines()]
    return [{"hash": r[0], "author": r[1], "date": r[2], "subject": r[3]} for r in rows if len(r) == 4]


async def status(path: Path) -> str:
    _, out = await _git(path, "status", "--short")
    return out
