from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import FeatureStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str
    description: str = ""
    specification: str = ""
    test_command: str = ""
    import_existing: bool = False


class ProjectUpdate(BaseModel):
    description: str | None = None
    specification: str | None = None
    test_command: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    path: str
    description: str
    specification: str
    test_command: str
    initialized: bool
    created_at: datetime


class FeatureCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    acceptance_criteria: list[str] = []
    priority: int = 100


class FeatureUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    acceptance_criteria: list[str] | None = None
    priority: int | None = None


class StatusUpdate(BaseModel):
    status: FeatureStatus


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    title: str
    description: str
    acceptance_criteria: list[str]
    priority: int
    sequence: int
    status: FeatureStatus
    attempts: int
    failure_reason: str
    seconds_spent: float
    completed_at: datetime | None
    depends_on: list[int] = []


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    kind: str
    status: str
    feature_id: int | None
    started_at: datetime
    ended_at: datetime | None
    error: str
    cost_usd: float
    turns: int


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int | None
    at: datetime
    level: str
    kind: str
    message: str


class TestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    feature_id: int | None
    session_id: int | None
    kind: str
    command: str
    exit_code: int
    duration_seconds: float
    output_tail: str
    at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    command: str
    reason: str
    status: str
    requested_at: datetime


class SettingsOut(BaseModel):
    api_key_configured: bool
    docker_available: bool
    docker_enabled: bool
    workspace_roots: list[str]
    model: str
    max_session_minutes: int
    max_turns_per_session: int
    max_consecutive_failures: int
    auto_commit: bool


class SettingsUpdate(BaseModel):
    model: str | None = None
    max_session_minutes: int | None = Field(default=None, ge=1, le=480)
    max_turns_per_session: int | None = Field(default=None, ge=1, le=500)
    max_consecutive_failures: int | None = Field(default=None, ge=1, le=20)
    auto_commit: bool | None = None
