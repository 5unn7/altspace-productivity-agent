"""Review + history routes — the weekly pattern review and the "this week" view.

Unlike the other feature routers, this one declares **no prefix**: each path is
spelled out in full (``/review/weekly``, ``/summaries``, ``/reviews``) to match
the API contract in BUILD-PLAN.md §4. ``main.py`` includes the router as-is.

  - POST /review/weekly  → run the LangGraph weekly-patterns path (the same code
                           APScheduler schedules; exposed as a manual button so
                           the demo never waits for Sunday) and return the
                           freshly-persisted WeeklyReview.
  - GET  /summaries      → the user's EOD summaries, newest first, optionally
                           windowed by ?from & ?to — powers the "This week" view.
  - GET  /reviews        → the user's weekly reviews, newest first.

Every query is scoped by ``current_user.id``. The client never supplies a user
id and can never read another user's history.

Seam contract this builds on:
  - app/security.py    → get_current_user
  - app/agent/graph.py → run_checkin(db, user_id, "weekly") persists a WeeklyReview
  - app/models.py      → EodSummary, WeeklyReview
  - app/schemas.py     → EodSummaryOut, WeeklyReviewOut
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agent.graph import run_checkin
from app.database import get_db
from app.models import EodSummary, User, WeeklyReview
from app.schemas import EodSummaryOut, WeeklyReviewOut
from app.security import get_current_user

# No prefix — the paths below are absolute, per the API contract.
router = APIRouter(tags=["review"])


@router.post(
    "/review/weekly",
    response_model=WeeklyReviewOut,
    summary="Run the weekly pattern review now and return the latest one",
)
def run_weekly_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WeeklyReview:
    """Trigger the agent's weekly-patterns path and return the persisted review.

    The agent reads the user's last 7 days, writes an AltSpace-voice pattern
    paragraph ("you pushed the gym four weeks running"), and persists a
    ``WeeklyReview`` row. We then read back the newest review for this user so
    the response always reflects what just landed in the DB. If the agent run
    fails (e.g. a free-tier LLM hiccup) we degrade to a clean 502 rather than a
    raw 500, and never leave a half-written transaction behind.
    """
    try:
        run_checkin(db, current_user.id, "weekly")
    except Exception as exc:  # noqa: BLE001 — convert any agent fault to a 502
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AltSpace couldn't finish the weekly review right now: {exc}",
        ) from exc

    review = (
        db.query(WeeklyReview)
        .filter(WeeklyReview.user_id == current_user.id)
        .order_by(WeeklyReview.created_at.desc(), WeeklyReview.id.desc())
        .first()
    )

    if review is None:
        # The agent should always persist a review; if it somehow produced none,
        # say so plainly instead of returning an empty 200 the client can't read.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The weekly review ran but produced no result to show.",
        )

    return review


@router.get(
    "/summaries",
    response_model=list[EodSummaryOut],
    summary="The user's end-of-day summaries, newest first (the 'This week' view)",
)
def list_summaries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    from_date: date | None = Query(
        default=None,
        alias="from",
        description="Only include summaries on or after this date (inclusive).",
    ),
    to_date: date | None = Query(
        default=None,
        alias="to",
        description="Only include summaries on or before this date (inclusive).",
    ),
) -> list[EodSummary]:
    """Return this user's EOD summaries, newest first, optionally date-windowed.

    ``from`` and ``to`` are both optional and inclusive. With neither, the full
    history is returned (newest first) — the frontend slices the current week.
    """
    query = db.query(EodSummary).filter(EodSummary.user_id == current_user.id)

    if from_date is not None:
        query = query.filter(EodSummary.summary_date >= from_date)
    if to_date is not None:
        query = query.filter(EodSummary.summary_date <= to_date)

    return (
        query.order_by(
            EodSummary.summary_date.desc(), EodSummary.id.desc()
        ).all()
    )


@router.get(
    "/reviews",
    response_model=list[WeeklyReviewOut],
    summary="The user's weekly reviews, newest first",
)
def list_reviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WeeklyReview]:
    """Return this user's weekly reviews, newest first."""
    return (
        db.query(WeeklyReview)
        .filter(WeeklyReview.user_id == current_user.id)
        .order_by(WeeklyReview.week_start.desc(), WeeklyReview.id.desc())
        .all()
    )
