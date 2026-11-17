"""Execution limits editable at runtime. Stored in the DB; env values are the defaults."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AppSetting


@dataclass
class Limits:
    model: str
    max_session_minutes: int
    max_turns_per_session: int
    max_consecutive_failures: int
    auto_commit: bool


_INT_KEYS = ("max_session_minutes", "max_turns_per_session", "max_consecutive_failures")


def load(db: Session) -> Limits:
    s = get_settings()
    rows = {r.key: r.value for r in db.query(AppSetting).all()}
    ints = {k: int(rows[k]) if k in rows else getattr(s, k) for k in _INT_KEYS}
    return Limits(model=rows.get("model", s.model), auto_commit=rows.get("auto_commit", "true") == "true", **ints)


def save(db: Session, values: dict[str, object]) -> Limits:
    for k, v in values.items():
        if v is None:
            continue
        row = db.get(AppSetting, k)
        text = ("true" if v else "false") if isinstance(v, bool) else str(v)
        if row:
            row.value = text
        else:
            db.add(AppSetting(key=k, value=text))
    db.flush()
    return load(db)
