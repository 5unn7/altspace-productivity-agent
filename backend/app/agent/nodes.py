"""LangGraph node functions — the agent's actual work.

Each node takes a request-scoped SQLAlchemy ``Session`` (bound in via
``functools.partial`` in graph.py) plus the rolling ``CheckinState`` and returns
a partial-state dict that LangGraph merges back into the channel state.

Design rules followed throughout:
  * Real Groq calls via app.llm (classifier for parsing, summary for prose).
  * Every value is validated against the tuples in app.models before it touches
    the DB — a hallucinated category/priority never reaches a column.
  * Nodes NEVER raise on empty/garbage input. A blank check-in or an unparseable
    model reply degrades to a sensible default, so the route layer never 500s.
  * All persistence is scoped to ``state["user_id"]`` — no cross-user leakage.
  * Voice: every LLM prompt instructs the model to speak as "AltSpace", a candid,
    concise chief of staff. Summaries stay to ~1 short paragraph.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.state import CheckinState, ParsedTask
from app.llm import chat_json, classifier_llm, summary_llm
from app.models import (
    CATEGORIES,
    PRIORITIES,
    DailyLog,
    EodSummary,
    Task,
    User,
    WeeklyReview,
)

logger = logging.getLogger("altspace.agent")

# AltSpace's identity, prepended to every prose generation. Cheap, high-impact:
# it's what makes the output feel like "someone you work with".
ALTSPACE_VOICE = (
    "You are AltSpace, the user's AI chief of staff. You are candid, concise, and "
    "warm — direct with no fluff, no corporate filler, no emoji. You speak in the "
    "first person ('I') and address the user as 'you'. You hold their context "
    "across days and tell them the truth about what got done and what slipped."
)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _today() -> date:
    return datetime.now(timezone.utc).date()


def _coerce_category(value: object) -> str:
    """Map a model-supplied category onto the allowed vocabulary, default 'other'."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in CATEGORIES:
            return v
    return "other"


def _coerce_priority(value: object) -> str:
    """Map a model-supplied priority onto the allowed vocabulary, default 'medium'."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in PRIORITIES:
            return v
    return "medium"


def _coerce_due_date(value: object, default: date) -> date:
    """Parse an ISO date string; fall back to ``default`` on anything odd."""
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return default
    return default


def _task_brief(task: Task) -> str:
    """One-line description of a task for stuffing into an LLM prompt."""
    due = task.due_date.isoformat() if task.due_date else "no date"
    return f"- {task.title} [{task.category}/{task.priority}] (due {due})"


# --------------------------------------------------------------------------- #
# MORNING: classify
# --------------------------------------------------------------------------- #
def classify(db: Session, state: CheckinState) -> dict:
    """Parse the morning brain-dump into structured tasks and persist them.

    Uses the fast classifier model. Persists a DailyLog of the raw text and one
    Task row per parsed item (source='morning', due_date defaults to today).
    Degrades to an empty task list — never raises — if the text is blank or the
    model returns nothing usable.
    """
    user_id = int(state["user_id"])
    raw_text = (state.get("raw_text") or "").strip()
    today = _today()

    # Always record the raw check-in (even if empty) so the day is on the books.
    db.add(DailyLog(user_id=user_id, log_date=today, kind="morning", raw_text=raw_text))

    parsed: list[ParsedTask] = []
    if raw_text:
        system = (
            "You extract a to-do list from a person's free-form morning brain-dump. "
            "Return ONLY a JSON object of the form "
            '{"tasks": [{"title": str, "category": one of '
            f"{list(CATEGORIES)}, \"priority\": one of {list(PRIORITIES)}, "
            '"due_date": "YYYY-MM-DD" or null}]}. '
            "Split distinct commitments into separate tasks. Keep each title short "
            "and action-oriented (imperative, e.g. 'Email the contractor'). Infer a "
            "sensible category and priority. If a day is mentioned ('tomorrow', "
            "'Friday') resolve it to a date relative to today; otherwise use null. "
            "Do not invent tasks the user did not mention. Output JSON only."
        )
        user = f"Today is {today.isoformat()}.\n\nBrain-dump:\n{raw_text}"
        try:
            data = chat_json(classifier_llm(), system, user)
        except Exception as exc:  # noqa: BLE001 — model/transport hiccup must not 500
            logger.warning("classify: LLM call failed, falling back to raw line: %s", exc)
            data = {}

        items = data.get("tasks")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = item.get("title")
                if not isinstance(title, str) or not title.strip():
                    continue
                parsed.append(
                    ParsedTask(
                        title=title.strip()[:500],
                        category=_coerce_category(item.get("category")),
                        priority=_coerce_priority(item.get("priority")),
                        due_date=item.get("due_date")
                        if isinstance(item.get("due_date"), str)
                        else None,
                    )
                )

        # Fallback: the model gave us nothing, but the user clearly typed *something*.
        # Treat the whole brain-dump as a single task rather than silently dropping it.
        if not parsed:
            parsed.append(
                ParsedTask(
                    title=raw_text[:500],
                    category="other",
                    priority="medium",
                    due_date=None,
                )
            )

    # Persist parsed tasks.
    created_titles: list[str] = []
    for p in parsed:
        due = _coerce_due_date(p.get("due_date"), default=today)
        db.add(
            Task(
                user_id=user_id,
                title=p["title"],
                category=p.get("category", "other"),
                priority=p.get("priority", "medium"),
                status="pending",
                source="morning",
                due_date=due,
            )
        )
        created_titles.append(p["title"])

    # Touch the streak: a morning check-in counts as showing up today.
    _bump_streak(db, user_id, today)

    db.commit()
    logger.info("classify: user=%s created %d task(s)", user_id, len(created_titles))
    return {"parsed_tasks": parsed}


# --------------------------------------------------------------------------- #
# MORNING: surface_overdue
# --------------------------------------------------------------------------- #
def surface_overdue(db: Session, state: CheckinState) -> dict:
    """Find still-pending tasks whose due_date is before today, mark them slipped.

    Returns a list of serialized, TaskOut-shaped dicts so the state stays JSON-
    clean for the checkpointer (ORM objects are not serializable into channels).
    """
    user_id = int(state["user_id"])
    today = _today()

    overdue_tasks = (
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.status == "pending")
            .where(Task.due_date.is_not(None))
            .where(Task.due_date < today)
            .order_by(Task.due_date.asc(), Task.priority.asc())
        )
        .scalars()
        .all()
    )

    serialized: list[dict] = []
    for t in overdue_tasks:
        t.status = "slipped"
        serialized.append(_serialize_task(t))

    if overdue_tasks:
        db.commit()
    logger.info("surface_overdue: user=%s marked %d slipped", user_id, len(serialized))
    return {"overdue": serialized}


# --------------------------------------------------------------------------- #
# EVENING: ingest_completions
# --------------------------------------------------------------------------- #
def ingest_completions(db: Session, state: CheckinState) -> dict:
    """Mark the user's completed_task_ids done, and log the evening recap.

    Strictly scoped to the user's own task ids — a client-supplied id belonging to
    another user simply doesn't match the WHERE clause and is ignored.
    """
    user_id = int(state["user_id"])
    today = _today()
    completed_ids = [int(i) for i in (state.get("completed_task_ids") or []) if _is_int(i)]
    raw_text = (state.get("raw_text") or "").strip()

    db.add(DailyLog(user_id=user_id, log_date=today, kind="evening", raw_text=raw_text))

    if completed_ids:
        tasks = (
            db.execute(
                select(Task)
                .where(Task.user_id == user_id)
                .where(Task.id.in_(completed_ids))
            )
            .scalars()
            .all()
        )
        now = datetime.now(timezone.utc)
        for t in tasks:
            t.status = "completed"
            t.completed_at = now

    _bump_streak(db, user_id, today)
    db.commit()
    logger.info(
        "ingest_completions: user=%s completed %d task(s)", user_id, len(completed_ids)
    )
    return {}


# --------------------------------------------------------------------------- #
# EVENING: eod_summary
# --------------------------------------------------------------------------- #
def eod_summary(db: Session, state: CheckinState) -> dict:
    """Draft a 1-paragraph candid EOD summary and persist an EodSummary row."""
    user_id = int(state["user_id"])
    today = _today()
    raw_text = (state.get("raw_text") or "").strip()

    todays_tasks = (
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.due_date == today)
        )
        .scalars()
        .all()
    )
    completed = [t for t in todays_tasks if t.status == "completed"]
    slipped = [t for t in todays_tasks if t.status in ("pending", "slipped")]

    stats = {
        "total": len(todays_tasks),
        "completed": len(completed),
        "slipped": len(slipped),
    }

    summary_text = _draft_eod_text(completed, slipped, raw_text, stats)

    db.add(
        EodSummary(
            user_id=user_id,
            summary_date=today,
            summary_text=summary_text,
            tomorrow_plan="",  # filled by plan_tomorrow once it runs
            stats_json=json.dumps(stats),
        )
    )
    db.commit()
    logger.info("eod_summary: user=%s wrote summary (%d done / %d slipped)",
                user_id, len(completed), len(slipped))
    return {"eod_summary": summary_text}


def _draft_eod_text(
    completed: list[Task],
    slipped: list[Task],
    raw_text: str,
    stats: dict,
) -> str:
    """One Groq call (summary tier) → candid 1-paragraph EOD recap."""
    if not completed and not slipped and not raw_text:
        return (
            "Quiet day on the board — nothing logged to close out. If you got things "
            "done off-list, tell me in the morning and I'll fold them in."
        )

    done_lines = "\n".join(_task_brief(t) for t in completed) or "(none marked done)"
    slip_lines = "\n".join(_task_brief(t) for t in slipped) or "(nothing left open)"
    recap = raw_text or "(no extra recap provided)"

    system = (
        ALTSPACE_VOICE
        + " Write the end-of-day summary as ONE short paragraph (2-4 sentences). "
        "Name what got done, call out what slipped without sugar-coating, and end on "
        "a forward note. No lists, no headers, no preamble — just the paragraph."
    )
    user = (
        f"Completed today:\n{done_lines}\n\n"
        f"Still open / slipped:\n{slip_lines}\n\n"
        f"User's own recap:\n{recap}\n\n"
        "Write the EOD summary now."
    )
    text = _summary_prose(system, user)
    if text:
        return text

    # Deterministic fallback if the model is unavailable — still useful, still in-voice.
    return (
        f"You closed {stats['completed']} of {stats['total']} today"
        + (f", and {stats['slipped']} slipped." if stats["slipped"] else ".")
        + " We pick those up tomorrow."
    )


# --------------------------------------------------------------------------- #
# EVENING: plan_tomorrow
# --------------------------------------------------------------------------- #
def plan_tomorrow(db: Session, state: CheckinState) -> dict:
    """Propose 3-6 tasks for tomorrow, persist them, and compose the plan text.

    Source material = today's slipped/pending work + the user's open high-priority
    backlog. New tasks are persisted with source='agent_planned', due tomorrow.
    """
    user_id = int(state["user_id"])
    today = _today()
    tomorrow = today + timedelta(days=1)

    # Open work that should carry forward: pending or slipped, due today or earlier,
    # plus any undated pending tasks. Highest priority first.
    carry = (
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.status.in_(("pending", "slipped")))
            .where((Task.due_date.is_(None)) | (Task.due_date <= today))
            .order_by(Task.priority.desc(), Task.due_date.asc().nulls_last())
        )
        .scalars()
        .all()
    )

    proposed = _propose_tomorrow_tasks(carry, today)

    created: list[ParsedTask] = []
    for p in proposed:
        db.add(
            Task(
                user_id=user_id,
                title=p["title"],
                category=p.get("category", "other"),
                priority=p.get("priority", "medium"),
                status="pending",
                source="agent_planned",
                due_date=tomorrow,
            )
        )
        created.append(p)

    plan_text = _compose_tomorrow_plan(created)

    # Backfill the plan onto today's EodSummary row so /summaries shows it.
    latest = (
        db.execute(
            select(EodSummary)
            .where(EodSummary.user_id == user_id)
            .where(EodSummary.summary_date == today)
            .order_by(EodSummary.id.desc())
        )
        .scalars()
        .first()
    )
    if latest is not None:
        latest.tomorrow_plan = plan_text

    db.commit()
    logger.info("plan_tomorrow: user=%s planned %d task(s)", user_id, len(created))
    return {"tomorrow_plan": plan_text, "tomorrow_tasks": created}


def _propose_tomorrow_tasks(carry: list[Task], today: date) -> list[ParsedTask]:
    """Ask the summary model to pick/shape 3-6 tasks for tomorrow.

    Falls back to simply carrying the top open tasks forward if the model is
    unavailable or returns nothing parseable.
    """
    if carry:
        carry_lines = "\n".join(_task_brief(t) for t in carry[:12])
        system = (
            ALTSPACE_VOICE
            + " Plan the user's tomorrow. From their open and slipped work, choose "
            "between 3 and 6 tasks that genuinely deserve tomorrow — prioritise what "
            "slipped and what's high priority. You may lightly rephrase a title to be "
            "crisp and actionable. Return ONLY JSON: "
            '{"tasks": [{"title": str, "category": one of '
            f"{list(CATEGORIES)}, \"priority\": one of {list(PRIORITIES)}}}]}}. "
            "Output JSON only."
        )
        user = f"Today is {today.isoformat()}.\n\nOpen / slipped work:\n{carry_lines}"
        try:
            data = chat_json(summary_llm(), system, user)
        except Exception as exc:  # noqa: BLE001
            logger.warning("plan_tomorrow: LLM call failed: %s", exc)
            data = {}

        items = data.get("tasks")
        out: list[ParsedTask] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = item.get("title")
                if not isinstance(title, str) or not title.strip():
                    continue
                out.append(
                    ParsedTask(
                        title=title.strip()[:500],
                        category=_coerce_category(item.get("category")),
                        priority=_coerce_priority(item.get("priority")),
                        due_date=None,
                    )
                )
                if len(out) >= 6:
                    break
        if out:
            return out

        # Model gave nothing usable → carry the top open tasks forward verbatim.
        return [
            ParsedTask(
                title=t.title[:500],
                category=t.category,
                priority=t.priority,
                due_date=None,
            )
            for t in carry[:5]
        ]

    # Nothing open to carry — seed one gentle planning nudge so tomorrow isn't blank.
    return [
        ParsedTask(
            title="Set your top 3 priorities for the day",
            category="work",
            priority="medium",
            due_date=None,
        )
    ]


def _compose_tomorrow_plan(tasks: list[ParsedTask]) -> str:
    """Short in-voice intro line + a tidy bulleted plan."""
    if not tasks:
        return "Tomorrow's open — tell me what matters and I'll shape the day."
    lines = "\n".join(f"  • {t['title']} [{t.get('priority', 'medium')}]" for t in tasks)
    return f"Here's tomorrow — {len(tasks)} to move:\n{lines}"


# --------------------------------------------------------------------------- #
# WEEKLY: weekly_patterns
# --------------------------------------------------------------------------- #
def weekly_patterns(db: Session, state: CheckinState) -> dict:
    """Summarize the last 7 days of tasks/logs into a patterns paragraph.

    Persists a WeeklyReview row. Honest fallback text if there's no data or the
    model is unavailable.
    """
    user_id = int(state["user_id"])
    today = _today()
    week_start = today - timedelta(days=6)

    tasks = (
        db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.created_at >= datetime.combine(week_start, datetime.min.time()))
            .order_by(Task.created_at.asc())
        )
        .scalars()
        .all()
    )
    logs = (
        db.execute(
            select(DailyLog)
            .where(DailyLog.user_id == user_id)
            .where(DailyLog.log_date >= week_start)
            .order_by(DailyLog.log_date.asc())
        )
        .scalars()
        .all()
    )

    stats = _week_stats(tasks)
    patterns_text = _draft_weekly_text(tasks, logs, stats, week_start, today)

    db.add(
        WeeklyReview(
            user_id=user_id,
            week_start=week_start,
            patterns_text=patterns_text,
            stats_json=json.dumps(stats),
        )
    )
    db.commit()
    logger.info("weekly_patterns: user=%s wrote review over %d task(s)", user_id, len(tasks))
    return {"patterns_text": patterns_text}


def _week_stats(tasks: list[Task]) -> dict:
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for t in tasks:
        by_category[t.category] = by_category.get(t.category, 0) + 1
        by_status[t.status] = by_status.get(t.status, 0) + 1
    completed = by_status.get("completed", 0)
    total = len(tasks)
    return {
        "total": total,
        "completed": completed,
        "slipped": by_status.get("slipped", 0),
        "completion_rate": round(completed / total, 2) if total else 0.0,
        "by_category": by_category,
    }


def _draft_weekly_text(
    tasks: list[Task],
    logs: list[DailyLog],
    stats: dict,
    week_start: date,
    today: date,
) -> str:
    if not tasks and not logs:
        return (
            "Not enough on the board this week to spot a pattern yet. Check in for a "
            "few days and I'll start showing you where your time actually goes."
        )

    task_lines = "\n".join(_task_brief(t) + f" — {t.status}" for t in tasks[:40])
    cat_mix = ", ".join(f"{k}: {v}" for k, v in stats["by_category"].items()) or "n/a"

    system = (
        ALTSPACE_VOICE
        + " Write a weekly pattern review as ONE short paragraph (3-5 sentences). "
        "Call out concrete patterns you actually see in the data — what they keep "
        "completing, what keeps slipping week over week, where their effort "
        "concentrates by category. Be specific and candid (e.g. 'health tasks slipped "
        "three days running'). No lists, no headers — just the paragraph."
    )
    user = (
        f"Window: {week_start.isoformat()} to {today.isoformat()}.\n"
        f"Completion rate: {stats['completion_rate']:.0%} "
        f"({stats['completed']}/{stats['total']}).\n"
        f"Category mix: {cat_mix}.\n\n"
        f"Tasks this week:\n{task_lines}\n\n"
        "Write the weekly pattern review now."
    )
    text = _summary_prose(system, user)
    if text:
        return text

    return (
        f"This week you logged {stats['total']} tasks and closed "
        f"{stats['completed']} ({stats['completion_rate']:.0%}). Your effort "
        f"concentrated in: {cat_mix}. Keep checking in and the trends sharpen."
    )


# --------------------------------------------------------------------------- #
# shared internals
# --------------------------------------------------------------------------- #
def _summary_prose(system: str, user: str) -> str:
    """Run the summary model for free-form prose; return '' on any failure.

    chat_json wants a JSON object, so we wrap the request: ask the model to put its
    paragraph under a "text" key. This reuses the hardened JSON extractor (fence
    stripping, brace slicing) instead of trusting raw content.
    """
    json_system = system + ' Respond ONLY as JSON: {"text": "<your paragraph>"}.'
    try:
        data = chat_json(summary_llm(), json_system, user)
    except Exception as exc:  # noqa: BLE001 — never let a model hiccup 500 the route
        logger.warning("_summary_prose: LLM call failed: %s", exc)
        return ""
    text = data.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""


def _serialize_task(t: Task) -> dict:
    """ORM Task → a JSON-safe, TaskOut-shaped dict for state channels."""
    return {
        "id": t.id,
        "title": t.title,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "source": t.source,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def _bump_streak(db: Session, user_id: int, today: date) -> None:
    """Increment the user's streak on the first check-in of a new day.

    Same-day repeat check-ins don't double-count. A gap of more than one day
    resets the streak to 1. Best-effort — a missing user is simply skipped.
    """
    user = db.get(User, user_id)
    if user is None:
        return
    last = user.last_checkin_date
    if last == today:
        return  # already counted today
    if last == today - timedelta(days=1):
        user.streak_count = (user.streak_count or 0) + 1
    else:
        user.streak_count = 1
    user.last_checkin_date = today


def _is_int(value: object) -> bool:
    try:
        int(value)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False
