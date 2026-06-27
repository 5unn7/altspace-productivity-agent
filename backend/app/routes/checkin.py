"""Check-in routes — the twice-a-day heartbeat of AltSpace.

Both endpoints are thin HTTP wrappers around the LangGraph agent. The agent
(``app.agent.graph.run_checkin``) owns all the intelligence + persistence:
parsing the brain-dump into tasks, surfacing what slipped, drafting the EOD
summary, and planning tomorrow. This module's job is narrow and well-defined:

  1. authenticate (``get_current_user``),
  2. hand the raw input to the agent scoped to ``current_user.id``,
  3. shape the agent's ORM output into a ``CheckinResult`` for the client,
  4. keep the user's streak honest (a check-in today keeps the streak alive).

Every query is scoped by ``current_user.id`` — the client never supplies a user
id, and never sees another user's tasks.

Seam contract this builds on:
  - app/security.py  → get_current_user (loads the User from the JWT)
  - app/agent/graph.py → run_checkin(db, user_id, kind, raw_text="",
                         completed_task_ids=None) -> dict with keys
                         message / planned_tasks / overdue / eod_summary /
                         tomorrow_plan / tomorrow_tasks  (Task ORM lists)
  - app/schemas.py   → MorningCheckinIn / EveningCheckinIn / CheckinResult / TaskOut
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.graph import run_checkin
from app.database import get_db
from app.models import User
from app.schemas import (
    CheckinResult,
    EveningCheckinIn,
    MorningCheckinIn,
    TaskOut,
)
from app.security import get_current_user

router = APIRouter(prefix="/checkin", tags=["checkin"])


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _tasks_out(items: list | None) -> list[TaskOut]:
    """Coerce a list of Task ORM objects (or None) into TaskOut models.

    The agent returns ORM instances; the API contract speaks TaskOut. We guard
    against a missing/None key so a sparse agent result never raises.
    """
    return [TaskOut.model_validate(obj) for obj in (items or [])]


def _bump_streak(user: User, today: date) -> None:
    """Keep the user's daily-check-in streak honest.

    Rules (consistent for morning and evening — the first check-in of the day
    is what advances the streak; a second check-in the same day is a no-op):

      - already checked in today      → leave the streak untouched.
      - last check-in was yesterday   → continue the streak (+1).
      - any other case (gap or first) → start a fresh streak at 1.

    Mutates ``user`` in place; the caller is responsible for committing.
    """
    last = user.last_checkin_date

    if last == today:
        # Second check-in of the day — streak already counted this morning.
        return

    if last == today - timedelta(days=1):
        user.streak_count = (user.streak_count or 0) + 1
    else:
        # First check-in ever, or the chain was broken by a missed day.
        user.streak_count = 1

    user.last_checkin_date = today


def _run_checkin_safe(
    db: Session,
    user_id: int,
    kind: str,
    *,
    raw_text: str = "",
    completed_task_ids: list[int] | None = None,
) -> dict:
    """Invoke the agent, translating any internal failure into a clean 502.

    The agent talks to a free-tier LLM (Groq), which can rate-limit or hiccup.
    We never want that to surface as an opaque 500 — a graded demo must degrade
    gracefully. A failed agent run rolls back the request's transaction so we
    don't leave half-written rows behind, then returns a readable error.
    """
    try:
        return run_checkin(
            db,
            user_id,
            kind,
            raw_text=raw_text,
            completed_task_ids=completed_task_ids,
        )
    except Exception as exc:  # noqa: BLE001 — convert any agent fault to a 502
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AltSpace couldn't finish that check-in right now: {exc}",
        ) from exc


# --------------------------------------------------------------------------- #
# routes                                                                       #
# --------------------------------------------------------------------------- #
@router.post(
    "/morning",
    response_model=CheckinResult,
    summary="Morning check-in — brain-dump in, classified plan + overdue out",
)
def morning_checkin(
    body: MorningCheckinIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckinResult:
    """Parse the morning brain-dump into tasks and surface what slipped.

    The agent classifies the free text into structured tasks, persists them,
    marks overdue pending tasks as ``slipped``, and writes an AltSpace-voice
    greeting. We then advance the user's streak and return the shaped result.
    """
    raw_text = (body.raw_text or "").strip()

    result = _run_checkin_safe(
        db,
        current_user.id,
        "morning",
        raw_text=raw_text,
    )

    # A check-in happened — keep the streak alive (idempotent within a day).
    _bump_streak(current_user, date.today())
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return CheckinResult(
        kind="morning",
        message=result.get("message") or "",
        planned_tasks=_tasks_out(result.get("planned_tasks")),
        overdue=_tasks_out(result.get("overdue")),
    )


@router.post(
    "/evening",
    response_model=CheckinResult,
    summary="Evening check-in — mark done, get an EOD summary + tomorrow's plan",
)
def evening_checkin(
    body: EveningCheckinIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckinResult:
    """Close out the day: mark completions, draft the EOD summary, plan tomorrow.

    The agent marks the supplied tasks complete, parses any tasks that emerged
    during the day, drafts the one-paragraph "done vs slipped" summary, and
    proposes tomorrow's tasks (persisted with ``source='agent_planned'``). Both
    inputs are optional — a blank evening check-in still produces a graceful
    summary, never a 500.
    """
    raw_text = (body.raw_text or "").strip()
    completed_task_ids = body.completed_task_ids or []

    result = _run_checkin_safe(
        db,
        current_user.id,
        "evening",
        raw_text=raw_text,
        completed_task_ids=completed_task_ids,
    )

    # The evening check-in also counts toward the streak (kept honest if the
    # user skipped the morning).
    _bump_streak(current_user, date.today())
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return CheckinResult(
        kind="evening",
        message=result.get("message") or "",
        eod_summary=result.get("eod_summary"),
        tomorrow_plan=result.get("tomorrow_plan"),
        tomorrow_tasks=_tasks_out(result.get("tomorrow_tasks")),
    )
