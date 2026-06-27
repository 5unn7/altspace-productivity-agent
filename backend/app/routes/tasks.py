"""Tasks CRUD router.

Owns the manual task lifecycle the user drives from the UI (the morning
check-in agent also writes tasks, but through the agent layer — these routes
are the direct CRUD surface). Every query is scoped by `current_user.id`; a
task that belongs to another user is indistinguishable from one that does not
exist, so cross-owner access returns 404, never 403.

Value vocabularies (category / priority / status) are validated against the
tuples in `app.models` so a typo can't poison the data — SQLite/Postgres store
them as plain strings, so the app layer is the only guardrail.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CATEGORIES, PRIORITIES, TASK_STATUSES, Task, User
from app.schemas import TaskCreate, TaskOut, TaskUpdate
from app.security import get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _reject_unless(value: str, allowed: tuple[str, ...], field: str) -> None:
    """422 if `value` is not one of `allowed`. Mirrors model value tuples."""
    if value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field} '{value}'. Allowed: {', '.join(allowed)}.",
        )


def _get_owned_task(db: Session, task_id: int, user_id: int) -> Task:
    """Load a task by id scoped to its owner, or raise 404.

    Scoping the lookup by `user_id` (not just the primary key) is what keeps a
    user from reading or mutating someone else's task — the row simply isn't
    found.
    """
    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by task status (pending | completed | slipped).",
    ),
    due_date: date | None = Query(
        default=None,
        alias="date",
        description="Filter by due date (YYYY-MM-DD).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Task]:
    """List the current user's tasks, newest first, with optional filters."""
    if status_filter is not None:
        _reject_unless(status_filter, TASK_STATUSES, "status")

    stmt = select(Task).where(Task.user_id == current_user.id)
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    if due_date is not None:
        stmt = stmt.where(Task.due_date == due_date)
    stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc())

    return list(db.scalars(stmt).all())


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Create a task owned by the current user (source defaults to 'morning')."""
    _reject_unless(payload.category, CATEGORIES, "category")
    _reject_unless(payload.priority, PRIORITIES, "priority")

    task = Task(
        user_id=current_user.id,
        title=payload.title,
        category=payload.category,
        priority=payload.priority,
        status="pending",
        source="morning",
        due_date=payload.due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Update fields on the current user's task.

    Only fields present in the request body are touched. Setting `status` to
    'completed' stamps `completed_at`; moving it back off 'completed' clears the
    stamp so a re-opened task doesn't carry a stale completion time.
    """
    task = _get_owned_task(db, task_id, current_user.id)
    fields = payload.model_dump(exclude_unset=True)

    if "category" in fields and fields["category"] is not None:
        _reject_unless(fields["category"], CATEGORIES, "category")
    if "priority" in fields and fields["priority"] is not None:
        _reject_unless(fields["priority"], PRIORITIES, "priority")
    if "status" in fields and fields["status"] is not None:
        _reject_unless(fields["status"], TASK_STATUSES, "status")

    for key, value in fields.items():
        # An explicit null on `title` would violate NOT NULL — skip it; nulls on
        # the optional columns (category/priority/status/due_date) are honored
        # only where they make sense, so guard title specifically.
        if key == "title" and value is None:
            continue
        setattr(task, key, value)

    new_status = fields.get("status")
    if new_status == "completed":
        if task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
    elif new_status is not None:
        # Re-opened or slipped — drop any prior completion stamp.
        task.completed_at = None

    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete the current user's task. 404 if it isn't theirs (or doesn't exist).

    Returns a bodyless 204. `response_class=Response` tells FastAPI there is
    genuinely no body to serialize (a plain `-> None` is treated as an implied
    body and trips the 204 "must not have a response body" assertion).
    """
    task = _get_owned_task(db, task_id, current_user.id)
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
