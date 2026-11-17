"""Environment-driven configuration. Secrets are only ever read from the environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ANTHROPIC_API_KEY is deliberately not a FORGEDESK_-prefixed setting: the Agent SDK reads it from the process
# environment, so a .env file must populate os.environ (existing variables win).
load_dotenv(".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FORGEDESK_", extra="ignore")

    database_url: str = "sqlite:///./forgedesk.db"
    # Directories under which projects may live. Every file operation is confined to them.
    workspace_roots: list[str] = Field(default_factory=lambda: [str(Path.home() / "forgedesk-projects")])
    model: str = "claude-sonnet-4-5"
    max_session_minutes: int = 45
    max_turns_per_session: int = 80
    max_consecutive_failures: int = 3
    backoff_base_seconds: float = 5.0
    backoff_max_seconds: float = 300.0
    use_docker: bool = False
    docker_image: str = "python:3.12-slim"
    approval_timeout_seconds: int = 600
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def roots(self) -> list[Path]:
        return [Path(r).expanduser().resolve() for r in self.workspace_roots]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def anthropic_api_key_configured() -> bool:
    import os

    return bool(os.environ.get("ANTHROPIC_API_KEY"))
