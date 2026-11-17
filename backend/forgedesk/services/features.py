"""Feature CRUD and dependency-aware scheduling."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Feature, FeatureDependency, FeatureStatus


class FeatureError(ValueError):
    pass


def dependency_map(db: Session, project_id: int) -> dict[int, set[int]]:
    ids = select(Feature.id).where(Feature.project_id == project_id)
    rows = db.execute(select(FeatureDependency).where(FeatureDependency.feature_id.in_(ids))).scalars()
    out: dict[int, set[int]] = {}
    for r in rows:
        out.setdefault(r.feature_id, set()).add(r.depends_on_id)
    return out


def would_cycle(deps: dict[int, set[int]], feature_id: int, depends_on_id: int) -> bool:
    """True if adding feature_id -> depends_on_id would create a cycle."""
    seen: set[int] = set()
    stack = [depends_on_id]
    while stack:
        cur = stack.pop()
        if cur == feature_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(deps.get(cur, ()))
    return False


def add_dependency(db: Session, feature_id: int, depends_on_id: int) -> None:
    a, b = db.get(Feature, feature_id), db.get(Feature, depends_on_id)
    if not a or not b or a.project_id != b.project_id:
        raise FeatureError("both features must exist in the same project")
    if feature_id == depends_on_id:
        raise FeatureError("a feature cannot depend on itself")
    if would_cycle(dependency_map(db, a.project_id), feature_id, depends_on_id):
        raise FeatureError("dependency would create a cycle")
    if not db.get(FeatureDependency, (feature_id, depends_on_id)):
        db.add(FeatureDependency(feature_id=feature_id, depends_on_id=depends_on_id))
        db.flush()
    refresh_blocked(db, a.project_id)


def remove_dependency(db: Session, feature_id: int, depends_on_id: int) -> None:
    row = db.get(FeatureDependency, (feature_id, depends_on_id))
    if row:
        db.delete(row)
        db.flush()
        f = db.get(Feature, feature_id)
        if f:
            refresh_blocked(db, f.project_id)


def refresh_blocked(db: Session, project_id: int) -> None:
    """A pending feature is blocked while any dependency has failed; it returns to pending once none has."""
    feats = {f.id: f for f in db.scalars(select(Feature).where(Feature.project_id == project_id))}
    deps = dependency_map(db, project_id)

    def blocked_by(fid: int, seen: frozenset[int] = frozenset()) -> int | None:
        for d in deps.get(fid, ()):
            if d in seen or d not in feats:
                continue
            if feats[d].status in (FeatureStatus.failed, FeatureStatus.blocked):
                return d
        return None

    for f in feats.values():
        culprit = blocked_by(f.id)
        if f.status == FeatureStatus.pending and culprit is not None:
            f.status = FeatureStatus.blocked
            f.failure_reason = f"blocked by '{feats[culprit].title}'"
        elif f.status == FeatureStatus.blocked and culprit is None:
            f.status = FeatureStatus.pending
            f.failure_reason = ""
    db.flush()


def eligible(db: Session, project_id: int) -> list[Feature]:
    """Pending features whose dependencies are all completed, in priority order."""
    feats = list(db.scalars(select(Feature).where(Feature.project_id == project_id)
                            .order_by(Feature.priority, Feature.sequence, Feature.id)))
    done = {f.id for f in feats if f.status == FeatureStatus.completed}
    deps = dependency_map(db, project_id)
    return [f for f in feats if f.status == FeatureStatus.pending and deps.get(f.id, set()) <= done]


def claim_next(db: Session, project_id: int, session_id: int, max_attempts: int = 3) -> Feature | None:
    """Atomically claim the next eligible feature.

    The UPDATE is a compare-and-swap on status, so two concurrent sessions can never claim the same row.
    """
    for f in eligible(db, project_id):
        if f.attempts >= max_attempts:
            continue
        res = db.execute(update(Feature)
                         .where(Feature.id == f.id, Feature.status == FeatureStatus.pending)
                         .values(status=FeatureStatus.in_progress, claimed_by_session=session_id,
                                 attempts=Feature.attempts + 1))
        db.flush()
        if res.rowcount == 1:
            db.refresh(f)
            return f
    return None


def finish(db: Session, feature_id: int, status: FeatureStatus, *, reason: str = "", seconds: float = 0.0) -> Feature:
    f = db.get(Feature, feature_id)
    if not f:
        raise FeatureError("feature not found")
    f.status = status
    f.claimed_by_session = None
    f.seconds_spent += seconds
    f.failure_reason = reason if status in (FeatureStatus.failed, FeatureStatus.blocked) else ""
    f.completed_at = datetime.now(UTC) if status == FeatureStatus.completed else None
    db.flush()
    refresh_blocked(db, f.project_id)
    return f


def set_status_manually(db: Session, feature_id: int, status: FeatureStatus) -> Feature:
    f = db.get(Feature, feature_id)
    if not f:
        raise FeatureError("feature not found")
    if f.status == FeatureStatus.in_progress and f.claimed_by_session is not None:
        raise FeatureError("feature is being worked on by an agent session; stop the agent first")
    if status == FeatureStatus.in_progress:
        raise FeatureError("in_progress is set only by an agent session")
    if status == FeatureStatus.pending:
        f.attempts = 0
    return finish(db, feature_id, status, reason="set manually" if status in (FeatureStatus.failed, FeatureStatus.blocked) else "")


def release_claims(db: Session, session_id: int) -> int:
    """Return features held by a dead/stopped session to pending."""
    res = db.execute(update(Feature).where(Feature.claimed_by_session == session_id,
                                           Feature.status == FeatureStatus.in_progress)
                     .values(status=FeatureStatus.pending, claimed_by_session=None))
    return res.rowcount or 0


def progress(db: Session, project_id: int) -> dict[str, int | float]:
    rows = db.execute(select(Feature.status, func.count()).where(Feature.project_id == project_id)
                      .group_by(Feature.status)).all()
    counts = {s.value: 0 for s in FeatureStatus}
    for s, n in rows:
        counts[s.value] = n
    total = sum(counts.values())
    return {**counts, "total": total, "percent": round(100 * counts["completed"] / total, 1) if total else 0.0}


def create_from_plan(db: Session, project_id: int, plan: list[dict]) -> list[Feature]:
    """Persist a feature plan. `depends_on` entries are 1-based indices into the plan. Duplicate titles are skipped."""
    existing = {t.lower() for t in db.scalars(select(Feature.title).where(Feature.project_id == project_id))}
    created: list[Feature | None] = []
    for i, item in enumerate(plan):
        title = str(item.get("title", "")).strip()[:200]
        if not title or title.lower() in existing:
            created.append(None)
            continue
        existing.add(title.lower())
        f = Feature(project_id=project_id, title=title, description=str(item.get("description", "")),
                    acceptance_criteria=[str(c) for c in item.get("acceptance_criteria", [])],
                    priority=int(item.get("priority", 100)), sequence=i)
        db.add(f)
        created.append(f)
    db.flush()
    for i, item in enumerate(plan):
        f = created[i]
        if f is None:
            continue
        for d in item.get("depends_on", []):
            try:
                target = created[int(d) - 1]
            except (IndexError, ValueError, TypeError):
                continue
            if target is not None and target.id != f.id:
                try:
                    add_dependency(db, f.id, target.id)
                except FeatureError:
                    continue  # drop edges that would form a cycle
    return [f for f in created if f]
