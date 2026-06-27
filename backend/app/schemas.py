"""Pydantic v2 schemas — the API contract.

Frontend (Streamlit) and the route layer both build against these. Field names
mirror models.py. `from_attributes=True` lets routes return ORM objects directly.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=120)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    name: str
    streak_count: int
    last_checkin_date: date | None = None


# ---------- tasks ----------
class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    category: str = "other"
    priority: str = "medium"
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    priority: str | None = None
    status: str | None = None  # pending | completed | slipped
    due_date: date | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category: str
    priority: str
    status: str
    source: str
    due_date: date | None = None
    created_at: datetime
    completed_at: datetime | None = None


# ---------- check-ins ----------
class MorningCheckinIn(BaseModel):
    raw_text: str = Field(min_length=1)


class EveningCheckinIn(BaseModel):
    raw_text: str = ""
    completed_task_ids: list[int] = Field(default_factory=list)


class CheckinResult(BaseModel):
    """Unified result for both check-ins (fields populated per kind)."""

    kind: str  # morning | evening
    message: str  # the AltSpace-voice paragraph shown to the user
    planned_tasks: list[TaskOut] = Field(default_factory=list)
    overdue: list[TaskOut] = Field(default_factory=list)
    eod_summary: str | None = None
    tomorrow_plan: str | None = None
    tomorrow_tasks: list[TaskOut] = Field(default_factory=list)


# ---------- summaries / reviews ----------
class EodSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    summary_date: date
    summary_text: str
    tomorrow_plan: str
    created_at: datetime


class WeeklyReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    week_start: date
    patterns_text: str
    created_at: datetime
