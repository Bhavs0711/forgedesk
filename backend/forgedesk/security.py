"""Path confinement and shell-command classification.

This is a policy layer, not a sandbox. Host execution is only as safe as these heuristics;
use FORGEDESK_USE_DOCKER=true for real isolation of test commands.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PathNotAllowed(ValueError):
    pass


def resolve_within(base: Path, candidate: str | os.PathLike[str]) -> Path:
    """Resolve `candidate` (relative to `base` if relative) and require it to stay inside `base`.

    Symlinks are resolved first, so a link pointing outside the base is rejected.
    """
    base = base.resolve()
    p = Path(candidate).expanduser()
    p = (base / p) if not p.is_absolute() else p
    resolved = p.resolve()
    if resolved != base and base not in resolved.parents:
        raise PathNotAllowed(f"{candidate!s} is outside {base}")
    return resolved


def resolve_in_roots(path: str, roots: list[Path]) -> Path:
    resolved = Path(path).expanduser().resolve()
    for root in roots:
        if resolved == root or root in resolved.parents:
            return resolved
    raise PathNotAllowed(f"{path} is not under an authorized workspace root")


class Verdict(str, Enum):
    allow = "allow"
    approve = "approve"  # needs explicit human approval
    deny = "deny"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str = ""


SAFE_COMMANDS = {
    "ls", "cat", "echo", "pwd", "mkdir", "touch", "cp", "head", "tail", "wc", "sort", "uniq", "diff",
    "grep", "rg", "find", "sed", "awk", "tr", "cut", "tee", "true", "false", "test", "which", "env",
    "python", "python3", "pip", "pip3", "pytest", "ruff", "mypy", "black", "uv",
    "node", "npm", "npx", "pnpm", "yarn", "tsc", "vite", "vitest", "eslint", "prettier",
    "make", "cargo", "go", "git", "date", "sleep", "cd",
}
HARD_DENY_COMMANDS = {
    "sudo", "su", "doas", "mkfs", "dd", "shutdown", "reboot", "halt", "poweroff", "mount", "umount",
    "chown", "iptables", "nc", "ncat", "ssh", "scp", "systemctl", "service", "crontab", "eval",
}
APPROVAL_COMMANDS = {"rm", "rmdir", "mv", "chmod", "kill", "pkill", "killall", "curl", "wget", "docker", "truncate"}
DESTRUCTIVE_GIT = {"reset", "clean", "push", "rebase", "checkout", "restore", "branch", "stash", "filter-branch", "gc"}
SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
SUBSHELL = re.compile(r"\$\(|`|<\(|>\(")


def _looks_like_path(tok: str) -> bool:
    return tok.startswith(("/", "~", "..")) or "/.." in tok or tok.startswith("-") and "=/" in tok


def classify_command(command: str, project_root: Path) -> Decision:
    """Classify a shell command line for an agent working in `project_root`."""
    if not command.strip():
        return Decision(Verdict.deny, "empty command")
    if SUBSHELL.search(command):
        return Decision(Verdict.approve, "command substitution cannot be analysed statically")
    needs_approval: list[str] = []
    for segment in SEGMENT_SPLIT.split(command.strip()):
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError:
            return Decision(Verdict.approve, "unparseable shell syntax")
        # drop leading VAR=value assignments
        while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
            tokens.pop(0)
        if not tokens:
            continue
        prog = os.path.basename(tokens[0])
        args = tokens[1:]
        if prog in HARD_DENY_COMMANDS:
            return Decision(Verdict.deny, f"'{prog}' is not permitted")
        if re.search(r">\s*/(?:etc|dev|usr|bin|sys|proc)\b", segment):
            return Decision(Verdict.deny, "redirect to a system path")
        for a in args:
            if _looks_like_path(a):
                target = a.split("=", 1)[-1]
                try:
                    resolve_within(project_root, target)
                except PathNotAllowed:
                    return Decision(Verdict.deny, f"path outside the project: {a}")
        if prog == "rm" and any(re.fullmatch(r"-[a-zA-Z]*[rRf][a-zA-Z]*", a) for a in args):
            needs_approval.append("recursive/forced delete")
        elif prog in APPROVAL_COMMANDS:
            needs_approval.append(f"'{prog}' can be destructive or reach the network")
        elif prog == "git":
            sub = next((a for a in args if not a.startswith("-")), "")
            if sub in DESTRUCTIVE_GIT or "--force" in args or "-f" in args:
                needs_approval.append(f"git {sub} can discard work or alter remotes")
        elif prog in ("pip", "pip3", "npm", "pnpm", "yarn") and any(a in ("install", "add", "i") for a in args):
            if any(a.startswith(("http", "git+")) for a in args):
                needs_approval.append("installing from a URL")
        elif prog not in SAFE_COMMANDS:
            needs_approval.append(f"unrecognised command '{prog}'")
    if needs_approval:
        return Decision(Verdict.approve, "; ".join(dict.fromkeys(needs_approval)))
    return Decision(Verdict.allow)


SECRET_PATTERN = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{10,}|ANTHROPIC_API_KEY\s*=\s*\S+)")


def redact(text: str) -> str:
    """Strip API keys from anything that is logged or sent to the browser."""
    return SECRET_PATTERN.sub("[redacted]", text)
