from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .agent.runner import AgentManager, recover_after_crash
from .api import agent as agent_api
from .api import projects as projects_api
from .config import get_settings
from .db import get_engine
from .security import PathNotAllowed, resolve_within

log = logging.getLogger("forgedesk")


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


def create_app(*, migrate: bool = True, agents: AgentManager | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if migrate:
            run_migrations()
        get_engine()
        log.info("crash recovery: %s", recover_after_crash())
        app.state.agents = agents or AgentManager()
        for root in get_settings().roots:
            root.mkdir(parents=True, exist_ok=True)
        yield
        await app.state.agents.shutdown()

    app = FastAPI(title="ForgeDesk", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(projects_api.router)
    app.include_router(agent_api.router)
    app.include_router(agent_api.ws_router)
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            """Serve built files, falling back to index.html so client-side routes survive a refresh."""
            if path.startswith(("api/", "ws/")):
                raise HTTPException(404)
            try:
                candidate = resolve_within(dist, path)
            except PathNotAllowed:
                raise HTTPException(404) from None
            return FileResponse(candidate if candidate.is_file() else dist / "index.html")
    return app


app = create_app()
