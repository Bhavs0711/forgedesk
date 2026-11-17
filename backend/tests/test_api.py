import pytest
from fastapi.testclient import TestClient

from forgedesk.agent.runner import AgentManager
from forgedesk.main import create_app


@pytest.fixture
def client(env):
    with TestClient(create_app(migrate=False, agents=AgentManager())) as c:
        yield c


def test_project_paths_confined(client, env, tmp_path):
    assert client.post("/api/projects", json={"name": "x", "path": "/etc/evil"}).status_code == 400
    assert client.post("/api/projects", json={"name": "x", "path": str(env / ".." / "esc")}).status_code == 400
    ok = client.post("/api/projects", json={"name": "x", "path": str(env / "x"), "test_command": "pytest"})
    assert ok.status_code == 201 and (env / "x").is_dir()
    assert client.post("/api/projects", json={"name": "x", "path": str(env / "y")}).status_code == 400  # dup name


def test_features_and_dependencies(client, env):
    pid = client.post("/api/projects", json={"name": "p", "path": str(env / "p")}).json()["id"]
    a = client.post(f"/api/projects/{pid}/features", json={"title": "A"}).json()["id"]
    b = client.post(f"/api/projects/{pid}/features", json={"title": "B"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/features", json={"title": "A"}).status_code == 409
    assert client.put(f"/api/projects/{pid}/features/{b}/dependencies/{a}").status_code == 204
    assert client.put(f"/api/projects/{pid}/features/{a}/dependencies/{b}").status_code == 400
    assert client.put(f"/api/projects/{pid}/features/{a}/status", json={"status": "in_progress"}).status_code == 409
    assert client.put(f"/api/projects/{pid}/features/{a}/status", json={"status": "completed"}).json()["status"] == "completed"
    feats = {f["title"]: f for f in client.get(f"/api/projects/{pid}/features").json()}
    assert feats["B"]["depends_on"] == [a]
    assert client.get(f"/api/projects/{pid}").json()["progress"]["percent"] == 50.0
    report = client.get(f"/api/projects/{pid}/report?format=md")
    assert "1/2 features completed" in report.text


def test_settings_never_expose_key(client):
    body = client.get("/api/settings").text
    assert "sk-ant" not in body and client.get("/api/settings").json()["api_key_configured"] is True
    r = client.put("/api/settings", json={"max_session_minutes": 10, "auto_commit": False})
    assert r.json()["max_session_minutes"] == 10 and r.json()["auto_commit"] is False
    assert client.put("/api/settings", json={"max_session_minutes": 0}).status_code == 422


def test_agent_start_requires_key(client, env, monkeypatch):
    pid = client.post("/api/projects", json={"name": "p", "path": str(env / "p")}).json()["id"]
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    r = client.post(f"/api/projects/{pid}/agent/start")
    assert r.status_code == 409 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    assert client.post(f"/api/projects/{pid}/agent/pause").status_code == 409


def test_websocket_receives_events(client, env):
    from forgedesk.services.events import emit
    pid = client.post("/api/projects", json={"name": "p", "path": str(env / "p")}).json()["id"]
    with client.websocket_connect(f"/ws/projects/{pid}") as ws:
        assert ws.receive_json()["type"] == "agent_status"
        client.portal.call(lambda: emit(pid, None, "hello sk-ant-abcdefghijklmnop", kind="log"))
        msg = ws.receive_json()
        assert msg["type"] == "log" and "sk-ant" not in msg["data"]["message"]
    assert "hello" in client.get(f"/api/projects/{pid}/events").json()[0]["message"]


def test_dotenv_populates_process_environment(tmp_path):
    """Run in a clean interpreter: importing forgedesk.config must export ANTHROPIC_API_KEY from .env."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-dotenv\n")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    out = subprocess.run([sys.executable, "-c", "import forgedesk.config as c; print(c.anthropic_api_key_configured())"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"
