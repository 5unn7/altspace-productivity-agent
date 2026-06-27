"""The LangGraph agent — StateGraph build, checkpointer, and run helper.

This is the heart of AltSpace. One ``StateGraph(CheckinState)`` with a durable
checkpointer (``thread_id = f"user-{user_id}"``) gives every user a single rolling
thread, so state carries forward across days — the "memory" the product promises.

Topology (conditional entry on ``kind``):

    morning  : classify ──▶ surface_overdue ──▶ END
    evening  : ingest_completions ──▶ eod_summary ──▶ plan_tomorrow ──▶ END
    weekly   : weekly_patterns ──▶ END

The request-scoped DB ``Session`` is bound into each node with
``functools.partial`` so nodes stay pure ``(state) -> dict`` callables from
LangGraph's point of view while still talking to the real database.

Checkpointer selection (cached once per process):
  * sqlite URL  → ``SqliteSaver`` over a persistent connection.
  * postgres URL → ``PostgresSaver`` (best-effort; needs libpq / a reachable DB).
  * anything that fails to construct → ``MemorySaver`` so the app always runs.

``run_checkin(...)`` is the single seam the route layer calls. It invokes the
graph, then re-reads the freshly-written rows from the DB so it can hand back
real ORM ``Task`` objects (routes convert them via ``TaskOut.model_validate``).
It never raises on empty input — a blank check-in returns a sensible message.
"""

from __future__ import annotations

import functools
import logging
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import nodes
from app.agent.state import CheckinState
from app.config import settings
from app.models import EodSummary, Task, User, WeeklyReview

logger = logging.getLogger("altspace.agent")

__all__ = ["run_checkin", "build_graph", "get_checkpointer"]


# --------------------------------------------------------------------------- #
# checkpointer (one durable instance per process)
# --------------------------------------------------------------------------- #
_checkpointer = None
_checkpointer_lock = threading.Lock()


def get_checkpointer():
    """Return the process-wide checkpointer, constructing it once.

    Mirrors the dev/prod DB split: SqliteSaver for a sqlite ``DATABASE_URL``,
    PostgresSaver for postgres, MemorySaver as the always-works fallback (used in
    local dev when libpq isn't present, or if the saver package is missing).
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    with _checkpointer_lock:
        if _checkpointer is not None:  # re-check under lock
            return _checkpointer
        _checkpointer = _build_checkpointer()
        return _checkpointer


def _build_checkpointer():
    url = settings.DATABASE_URL

    if url.startswith("sqlite"):
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            path = _sqlite_path(url)
            # check_same_thread=False: FastAPI serves requests on a threadpool and
            # the saver is shared across them. The connection is long-lived for the
            # life of the process (one durable checkpoint store).
            conn = sqlite3.connect(path, check_same_thread=False)
            saver = SqliteSaver(conn)
            logger.info("Checkpointer: SqliteSaver at %s", path)
            return saver
        except Exception as exc:  # noqa: BLE001 — always degrade to a working saver
            logger.warning("SqliteSaver unavailable (%s); using MemorySaver", exc)
            return MemorySaver()

    # Postgres (or anything non-sqlite): try the Postgres saver, fall back cleanly.
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        saver_cm = PostgresSaver.from_conn_string(url)
        saver = saver_cm.__enter__()  # keep the connection open for the process
        saver.setup()  # idempotent: create checkpoint tables if missing
        logger.info("Checkpointer: PostgresSaver")
        return saver
    except Exception as exc:  # noqa: BLE001 — missing pkg / libpq / unreachable DB
        logger.warning("PostgresSaver unavailable (%s); using MemorySaver", exc)
        return MemorySaver()


def _sqlite_path(url: str) -> str:
    """Extract the filesystem path from a sqlite SQLAlchemy URL.

    'sqlite:///./altspace.db' -> './altspace.db'; 'sqlite://' (in-memory) -> ':memory:'.
    A dedicated checkpoint file is used so LangGraph's bookkeeping never collides
    with the app's own tables.
    """
    rest = url.split("sqlite:///", 1)[-1] if "sqlite:///" in url else ""
    if not rest:
        return ":memory:"
    # Keep checkpoints beside the app DB but in their own file.
    if rest.endswith(".db"):
        return rest[:-3] + ".checkpoints.db"
    return rest + ".checkpoints"


# --------------------------------------------------------------------------- #
# graph build
# --------------------------------------------------------------------------- #
def _route_by_kind(state: CheckinState) -> str:
    """Conditional entry: pick the path for this check-in's ``kind``."""
    kind = state.get("kind")
    if kind == "evening":
        return "ingest_completions"
    if kind == "weekly":
        return "weekly_patterns"
    return "classify"  # default + 'morning'


def build_graph(db: Session):
    """Build and compile the StateGraph with ``db`` bound into every node.

    The topology is static; only the bound Session changes per request, so this is
    cheap to call per invocation. The (expensive, stateful) checkpointer is shared.
    """
    bind = functools.partial  # node = partial(node_fn, db) → callable(state) -> dict

    graph = StateGraph(CheckinState)

    # nodes (db bound in)
    graph.add_node("classify", bind(nodes.classify, db))
    graph.add_node("surface_overdue", bind(nodes.surface_overdue, db))
    graph.add_node("ingest_completions", bind(nodes.ingest_completions, db))
    graph.add_node("eod_summary", bind(nodes.eod_summary, db))
    graph.add_node("plan_tomorrow", bind(nodes.plan_tomorrow, db))
    graph.add_node("weekly_patterns", bind(nodes.weekly_patterns, db))

    # conditional entry by kind
    graph.add_conditional_edges(
        START,
        _route_by_kind,
        {
            "classify": "classify",
            "ingest_completions": "ingest_completions",
            "weekly_patterns": "weekly_patterns",
        },
    )

    # morning path
    graph.add_edge("classify", "surface_overdue")
    graph.add_edge("surface_overdue", END)

    # evening path
    graph.add_edge("ingest_completions", "eod_summary")
    graph.add_edge("eod_summary", "plan_tomorrow")
    graph.add_edge("plan_tomorrow", END)

    # weekly path
    graph.add_edge("weekly_patterns", END)

    return graph.compile(checkpointer=get_checkpointer())


# --------------------------------------------------------------------------- #
# run helper (the route-layer seam)
# --------------------------------------------------------------------------- #
def run_checkin(
    db: Session,
    user_id: int,
    kind: str,
    raw_text: str = "",
    completed_task_ids: list[int] | None = None,
) -> dict:
    """Invoke the agent for one check-in and return the seam-contract dict.

    Returns keys: ``message`` (AltSpace-voice str), ``planned_tasks`` (Task ORM
    list), ``overdue`` (Task ORM list), ``eod_summary`` (str|None),
    ``tomorrow_plan`` (str|None), ``tomorrow_tasks`` (Task ORM list).

    Robust by construction: empty input never raises. If the graph itself fails
    (e.g. Groq is down), we degrade to a sensible in-voice message and whatever
    rows did get written.
    """
    kind = (kind or "morning").strip().lower()
    if kind not in ("morning", "evening", "weekly"):
        kind = "morning"

    initial: CheckinState = {
        "user_id": int(user_id),
        "kind": kind,  # type: ignore[typeddict-item]
        "raw_text": raw_text or "",
        "completed_task_ids": list(completed_task_ids or []),
    }
    config = {"configurable": {"thread_id": f"user-{user_id}"}}

    final_state: CheckinState
    try:
        app = build_graph(db)
        final_state = app.invoke(initial, config=config)  # type: ignore[assignment]
    except Exception as exc:  # noqa: BLE001 — the route must always get a usable result
        logger.exception("run_checkin failed for user=%s kind=%s: %s", user_id, kind, exc)
        db.rollback()
        final_state = dict(initial)  # type: ignore[assignment]

    # Re-read real ORM rows so the route can TaskOut.model_validate(obj). The state
    # channels hold JSON-safe dicts (for the checkpointer); the DB holds the truth.
    return _assemble_result(db, user_id, kind, final_state)


def _assemble_result(
    db: Session,
    user_id: int,
    kind: str,
    state: CheckinState,
) -> dict:
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)

    planned_tasks: list[Task] = []
    overdue: list[Task] = []
    tomorrow_tasks: list[Task] = []
    eod_text: str | None = None
    tomorrow_plan: str | None = None

    if kind == "morning":
        planned_tasks = _todays_morning_tasks(db, user_id, today)
        overdue = _slipped_tasks(db, user_id, today)
        message = _morning_message(planned_tasks, overdue)

    elif kind == "evening":
        eod_text = state.get("eod_summary") or _latest_eod_text(db, user_id, today)
        tomorrow_plan = state.get("tomorrow_plan") or _latest_tomorrow_plan(db, user_id, today)
        tomorrow_tasks = _tomorrows_planned_tasks(db, user_id, tomorrow)
        message = _evening_message(eod_text, tomorrow_tasks)

    else:  # weekly
        patterns = state.get("patterns_text") or _latest_weekly_text(db, user_id)
        message = patterns or (
            "Not enough logged this week to call a pattern yet — keep checking in."
        )

    return {
        "message": message,
        "planned_tasks": planned_tasks,
        "overdue": overdue,
        "eod_summary": eod_text,
        "tomorrow_plan": tomorrow_plan,
        "tomorrow_tasks": tomorrow_tasks,
    }


# ---- DB re-reads (scoped to user_id) ----
def _todays_morning_tasks(db: Session, user_id: int, today: date) -> list[Task]:
    return list(
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.source == "morning")
            .where(Task.due_date == today)
            .order_by(Task.priority.desc(), Task.id.asc())
        )
        .scalars()
        .all()
    )


def _slipped_tasks(db: Session, user_id: int, today: date) -> list[Task]:
    return list(
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.status == "slipped")
            .where(Task.due_date.is_not(None))
            .where(Task.due_date < today)
            .order_by(Task.due_date.asc(), Task.priority.desc())
        )
        .scalars()
        .all()
    )


def _tomorrows_planned_tasks(db: Session, user_id: int, tomorrow: date) -> list[Task]:
    return list(
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.source == "agent_planned")
            .where(Task.due_date == tomorrow)
            .order_by(Task.priority.desc(), Task.id.asc())
        )
        .scalars()
        .all()
    )


def _latest_eod_text(db: Session, user_id: int, today: date) -> str | None:
    row = (
        db.execute(
            select(EodSummary)
            .where(EodSummary.user_id == user_id)
            .where(EodSummary.summary_date == today)
            .order_by(EodSummary.id.desc())
        )
        .scalars()
        .first()
    )
    return row.summary_text if row else None


def _latest_tomorrow_plan(db: Session, user_id: int, today: date) -> str | None:
    row = (
        db.execute(
            select(EodSummary)
            .where(EodSummary.user_id == user_id)
            .where(EodSummary.summary_date == today)
            .order_by(EodSummary.id.desc())
        )
        .scalars()
        .first()
    )
    return (row.tomorrow_plan or None) if row else None


def _latest_weekly_text(db: Session, user_id: int) -> str | None:
    row = (
        db.execute(
            select(WeeklyReview)
            .where(WeeklyReview.user_id == user_id)
            .order_by(WeeklyReview.id.desc())
        )
        .scalars()
        .first()
    )
    return row.patterns_text if row else None


# ---- message composition (AltSpace voice) ----
def _morning_message(planned: list[Task], overdue: list[Task]) -> str:
    if not planned and not overdue:
        return (
            "Morning. Nothing landed on the board yet — give me a quick brain-dump "
            "of what's on your plate and I'll sort it into a plan."
        )

    parts: list[str] = ["Morning — here's where you stand."]
    if planned:
        n = len(planned)
        parts.append(
            f"I logged {n} task{'s' if n != 1 else ''} for today" + _top_titles(planned) + "."
        )
    if overdue:
        n = len(overdue)
        parts.append(
            f"Heads up: {n} thing{'s' if n != 1 else ''} slipped from before"
            + _top_titles(overdue)
            + " — let's clear those first."
        )
    else:
        parts.append("Nothing overdue dragging behind you. Clean slate.")
    return " ".join(parts)


def _evening_message(eod_text: str | None, tomorrow_tasks: list[Task]) -> str:
    pieces: list[str] = []
    if eod_text:
        pieces.append(eod_text)
    if tomorrow_tasks:
        n = len(tomorrow_tasks)
        pieces.append(
            f"I've teed up {n} task{'s' if n != 1 else ''} for tomorrow"
            + _top_titles(tomorrow_tasks)
            + "."
        )
    if not pieces:
        return (
            "Day closed out. Nothing to summarise tonight — check in tomorrow morning "
            "and we'll build the plan."
        )
    return " ".join(pieces)


def _top_titles(tasks: list[Task], limit: int = 3) -> str:
    """' (Email the contractor, Gym, +2 more)' style trailer for a message."""
    if not tasks:
        return ""
    shown = [t.title for t in tasks[:limit]]
    extra = len(tasks) - len(shown)
    trailer = ", ".join(shown)
    if extra > 0:
        trailer += f", +{extra} more"
    return f" ({trailer})"
