import json

import pytest

from forgedesk import config, db
from forgedesk.db import Base


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("FORGEDESK_DATABASE_URL", f"sqlite:///{tmp_path/'t.db'}")
    monkeypatch.setenv("FORGEDESK_WORKSPACE_ROOTS", json.dumps([str(root)]))
    monkeypatch.setenv("FORGEDESK_BACKOFF_BASE_SECONDS", "0.01")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-should-never-leak")
    config.get_settings.cache_clear()
    engine = db.init_engine()
    Base.metadata.create_all(engine)
    yield root
    engine.dispose()
    config.get_settings.cache_clear()
