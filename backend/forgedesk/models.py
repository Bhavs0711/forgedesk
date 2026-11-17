from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class FeatureStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"


class SessionStatus(str, enum.Enum):
    running = "running"
    paused = "paused"
    completed = "completed"
    stopped = "stopped"
    failed = "failed"
    interrupted = "interrupted"  # process died while running; recovered on startup


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    specification: Mapped[str] = mapped_column(Text, default="")
    test_command: Mapped[str] = mapped_column(String(500), default="")
    initialized: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    features: Mapped[list[Feature]] = relationship(back_populates="project", cascade="all, delete-orphan")
    sessions: Mapped[list[AgentSession]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Feature(Base):
    __tablename__ = "features"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower = sooner
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[FeatureStatus] = mapped_column(Enum(FeatureStatus), default=FeatureStatus.pending, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    claimed_by_session: Mapped[int | None] = mapped_column(ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True)
    seconds_spent: Mapped[float] = mapped_column(default=0.0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project: Mapped[Project] = relationship(back_populates="features")
    __table_args__ = (UniqueConstraint("project_id", "title", name="uq_feature_title"),)


class FeatureDependency(Base):
    __tablename__ = "feature_dependencies"
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), primary_key=True)


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="coding")  # initializer | coding | regression
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.running)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="SET NULL"), nullable=True)
    sdk_session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    turns: Mapped[int] = mapped_column(Integer, default=0)
    project: Mapped[Project] = relationship(back_populates="sessions")
    # Database-level guarantee: at most one live session per project, even across processes.
    __table_args__ = (Index("uq_one_live_session", "project_id", unique=True,
                            sqlite_where=text("status IN ('running', 'paused')")),)


class SessionEvent(Base):
    """Append-only activity timeline: logs, tool calls, status changes, errors."""

    __tablename__ = "session_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info | warn | error
    kind: Mapped[str] = mapped_column(String(30), default="log")
    message: Mapped[str] = mapped_column(Text)


class TestRun(Base):
    __tablename__ = "test_runs"
    __test__ = False
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id", ondelete="SET NULL"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="feature")  # feature | regression
    command: Mapped[str] = mapped_column(String(500))
    exit_code: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    output_tail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=True)
    command: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.pending)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
