from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AgentSession, Feature, Project, TestRun
from . import features as feat


def build_report(db: Session, project: Project) -> dict:
    feats = list(db.scalars(select(Feature).where(Feature.project_id == project.id).order_by(Feature.priority, Feature.sequence)))
    sessions = list(db.scalars(select(AgentSession).where(AgentSession.project_id == project.id).order_by(AgentSession.id)))
    runs = db.execute(select(func.count(), func.coalesce(func.sum(TestRun.exit_code == 0), 0))
                      .where(TestRun.project_id == project.id)).one()
    return {
        "project": {"name": project.name, "description": project.description, "path": project.path},
        "progress": feat.progress(db, project.id),
        "features": [{"id": f.id, "title": f.title, "status": f.status.value, "priority": f.priority,
                      "attempts": f.attempts, "seconds_spent": round(f.seconds_spent, 1),
                      "failure_reason": f.failure_reason} for f in feats],
        "sessions": [{"id": s.id, "kind": s.kind, "status": s.status.value, "started_at": s.started_at.isoformat(),
                      "ended_at": s.ended_at.isoformat() if s.ended_at else None, "turns": s.turns,
                      "cost_usd": round(s.cost_usd, 4), "error": s.error} for s in sessions],
        "tests": {"runs": runs[0], "passed": int(runs[1])},
        "totals": {"cost_usd": round(sum(s.cost_usd for s in sessions), 4),
                   "feature_seconds": round(sum(f.seconds_spent for f in feats), 1)},
    }


def to_markdown(r: dict) -> str:
    p = r["progress"]
    lines = [f"# {r['project']['name']} - development report", "",
             (f"Progress: {p['completed']}/{p['total']} features completed ({p['percent']}%). "
              f"Failed: {p['failed']}, blocked: {p['blocked']}, pending: {p['pending']}, in progress: {p['in_progress']}."),
             (f"Test runs: {r['tests']['passed']} passed of {r['tests']['runs']}. "
              f"Agent cost: ${r['totals']['cost_usd']:.4f}."), "", "## Features", "",
             "| # | Feature | Status | Attempts | Time (s) |", "|---|---|---|---|---|"]
    lines += [f"| {f['id']} | {f['title']} | {f['status']} | {f['attempts']} | {f['seconds_spent']} |" for f in r["features"]]
    lines += ["", "## Sessions", "", "| # | Kind | Status | Turns | Cost (USD) |", "|---|---|---|---|---|"]
    lines += [f"| {s['id']} | {s['kind']} | {s['status']} | {s['turns']} | {s['cost_usd']} |" for s in r["sessions"]]
    return "\n".join(lines) + "\n"
