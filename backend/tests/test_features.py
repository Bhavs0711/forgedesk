import pytest

from forgedesk.db import session_scope
from forgedesk.models import AgentSession, Feature, FeatureStatus, Project
from forgedesk.services import features as feat


def make_project(db, root):
    p = Project(name="p", path=str(root / "p"))
    db.add(p)
    db.flush()
    return p


def test_dependency_scheduling_and_cycles(env):
    with session_scope() as db:
        p = make_project(db, env)
        a, b, c = (Feature(project_id=p.id, title=t, priority=pr) for t, pr in (("a", 2), ("b", 1), ("c", 3)))
        db.add_all([a, b, c])
        db.flush()
        feat.add_dependency(db, b.id, a.id)  # b needs a, though b has better priority
        with pytest.raises(feat.FeatureError):
            feat.add_dependency(db, a.id, b.id)  # cycle
        with pytest.raises(feat.FeatureError):
            feat.add_dependency(db, a.id, a.id)
        assert [f.title for f in feat.eligible(db, p.id)] == ["a", "c"]
        feat.finish(db, a.id, FeatureStatus.completed)
        assert [f.title for f in feat.eligible(db, p.id)] == ["b", "c"]


def test_claim_is_exclusive(env):
    with session_scope() as db:
        p = make_project(db, env)
        db.add(Feature(project_id=p.id, title="only"))
        s1, s2 = AgentSession(project_id=p.id), AgentSession(project_id=p.id, kind="x", status="completed")
        db.add_all([s1, s2])
        db.flush()
        first = feat.claim_next(db, p.id, s1.id)
        second = feat.claim_next(db, p.id, s2.id)
        assert first is not None and first.status == FeatureStatus.in_progress and first.attempts == 1
        assert second is None


def test_failure_blocks_dependents_and_recovers(env):
    with session_scope() as db:
        p = make_project(db, env)
        a, b = Feature(project_id=p.id, title="a"), Feature(project_id=p.id, title="b")
        db.add_all([a, b])
        db.flush()
        feat.add_dependency(db, b.id, a.id)
        feat.finish(db, a.id, FeatureStatus.failed, reason="boom")
        assert b.status == FeatureStatus.blocked
        feat.set_status_manually(db, a.id, FeatureStatus.pending)
        assert b.status == FeatureStatus.pending and a.attempts == 0


def test_manual_status_rules(env):
    with session_scope() as db:
        p = make_project(db, env)
        f = Feature(project_id=p.id, title="a")
        db.add(f)
        db.flush()
        with pytest.raises(feat.FeatureError):
            feat.set_status_manually(db, f.id, FeatureStatus.in_progress)


def test_plan_dedupes_and_drops_cycles(env):
    with session_scope() as db:
        p = make_project(db, env)
        plan = [{"title": "A", "depends_on": [2]}, {"title": "B", "depends_on": [1]}, {"title": "a"}, {"title": ""}]
        created = feat.create_from_plan(db, p.id, plan)
        assert [f.title for f in created] == ["A", "B"]
        deps = feat.dependency_map(db, p.id)
        assert sum(len(v) for v in deps.values()) == 1  # second edge would form a cycle and is dropped
