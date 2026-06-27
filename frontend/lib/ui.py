"""Small render helpers for the AltSpace Streamlit UI.

These keep ``streamlit_app.py`` readable: task cards (colored by category,
badged by priority and urgency), summary panels, and section headers. They
return HTML strings rendered via ``st.markdown(..., unsafe_allow_html=True)`` so
the visual language stays consistent and dense — a power tool, not a dashboard.

No backend calls happen here; everything operates on plain dicts shaped like the
API's ``TaskOut`` / ``EodSummaryOut`` / ``WeeklyReviewOut`` responses.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any

import streamlit as st

# --- palette -------------------------------------------------------------- #
# Each category gets a calm, distinct accent. Status/priority reuse the
# semantic set (green=done, amber=active, red=urgent, gray=muted).
CATEGORY_COLORS: dict[str, str] = {
    "work": "#5b9bd5",      # blue
    "personal": "#c084e8",  # violet
    "health": "#4fbf8b",    # green
    "learning": "#f5a623",  # amber
    "other": "#8a8f99",     # gray
}

PRIORITY_COLORS: dict[str, str] = {
    "high": "#e5534b",   # red
    "medium": "#f5a623", # amber
    "low": "#6b7280",    # gray
}

STATUS_COLORS: dict[str, str] = {
    "pending": "#9aa0aa",
    "completed": "#4fbf8b",
    "slipped": "#e5534b",
}

STATUS_LABELS: dict[str, str] = {
    "pending": "Pending",
    "completed": "Done",
    "slipped": "Slipped",
}

CATEGORY_EMOJI: dict[str, str] = {
    "work": "💼",
    "personal": "🏠",
    "health": "🩺",
    "learning": "📚",
    "other": "•",
}


# --- small utilities ------------------------------------------------------ #
def _esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _due_label(due_value: Any) -> tuple[str, str]:
    """Return (text, color) describing a due date relative to today."""
    due = _parse_date(due_value)
    if due is None:
        return ("No due date", "#6b7280")
    delta = (due - date.today()).days
    if delta < 0:
        n = abs(delta)
        return (f"Overdue {n}d", "#e5534b")
    if delta == 0:
        return ("Due today", "#f5a623")
    if delta == 1:
        return ("Due tomorrow", "#5b9bd5")
    return (f"Due in {delta}d", "#9aa0aa")


def _pill(text: str, color: str, *, filled: bool = False) -> str:
    if filled:
        return (
            f"<span style='display:inline-block;padding:1px 8px;border-radius:10px;"
            f"background:{color};color:#0e0f12;font-size:11px;font-weight:600;"
            f"line-height:18px;'>{_esc(text)}</span>"
        )
    return (
        f"<span style='display:inline-block;padding:1px 8px;border-radius:10px;"
        f"border:1px solid {color};color:{color};font-size:11px;font-weight:600;"
        f"line-height:18px;'>{_esc(text)}</span>"
    )


# --- public render helpers ------------------------------------------------ #
def section_header(title: str, subtitle: str | None = None) -> None:
    """A dense, left-aligned section header (no hero banners)."""
    sub = (
        f"<div style='color:#9aa0aa;font-size:13px;margin-top:2px;'>"
        f"{_esc(subtitle)}</div>"
        if subtitle
        else ""
    )
    st.markdown(
        f"<div style='margin:4px 0 10px 0;'>"
        f"<div style='font-size:18px;font-weight:700;letter-spacing:.2px;'>"
        f"{_esc(title)}</div>{sub}</div>",
        unsafe_allow_html=True,
    )


def task_card(task: dict[str, Any]) -> None:
    """Render one task as a compact card: category stripe + title + badges."""
    category = str(task.get("category", "other"))
    priority = str(task.get("priority", "medium"))
    status = str(task.get("status", "pending"))
    title = task.get("title", "(untitled)")
    source = str(task.get("source", ""))

    cat_color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["other"])
    pri_color = PRIORITY_COLORS.get(priority, PRIORITY_COLORS["medium"])
    status_color = STATUS_COLORS.get(status, "#9aa0aa")
    emoji = CATEGORY_EMOJI.get(category, "•")

    due_text, due_color = _due_label(task.get("due_date"))
    completed = status == "completed"
    title_style = (
        "text-decoration:line-through;color:#7d828c;"
        if completed
        else "color:#e7e9ee;"
    )

    badges = [
        _pill(priority.upper(), pri_color),
        _pill(STATUS_LABELS.get(status, status), status_color),
        _pill(due_text, due_color),
    ]
    if source == "agent_planned":
        badges.append(_pill("AltSpace", "#f5a623", filled=True))
    elif source == "emerged":
        badges.append(_pill("Emerged", "#8a8f99"))

    badge_html = "&nbsp;".join(badges)

    st.markdown(
        f"<div style='display:flex;gap:10px;align-items:flex-start;"
        f"background:#1f232b;border-left:3px solid {cat_color};"
        f"border-radius:8px;padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='font-size:15px;line-height:22px;'>{emoji}</div>"
        f"<div style='flex:1;min-width:0;'>"
        f"<div style='font-size:14px;font-weight:600;{title_style}"
        f"word-break:break-word;'>{_esc(title)}</div>"
        f"<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;"
        f"align-items:center;'>"
        f"<span style='color:{cat_color};font-size:11px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:.4px;'>{_esc(category)}</span>"
        f"{badge_html}</div></div></div>",
        unsafe_allow_html=True,
    )


def empty_state(message: str, hint: str | None = None) -> None:
    """Honest empty state — no fake data, just a calm nudge."""
    hint_html = (
        f"<div style='color:#7d828c;font-size:12px;margin-top:4px;'>{_esc(hint)}</div>"
        if hint
        else ""
    )
    st.markdown(
        f"<div style='border:1px dashed #353a44;border-radius:8px;"
        f"padding:18px;text-align:center;color:#9aa0aa;font-size:13px;'>"
        f"{_esc(message)}{hint_html}</div>",
        unsafe_allow_html=True,
    )


def altspace_message(message: str) -> None:
    """Render an AltSpace-voice paragraph in a distinct, branded panel."""
    if not message:
        return
    st.markdown(
        f"<div style='background:#1b1f27;border:1px solid #2c3240;"
        f"border-left:3px solid #f5a623;border-radius:8px;padding:12px 14px;"
        f"margin:6px 0 12px 0;'>"
        f"<div style='color:#f5a623;font-size:11px;font-weight:700;"
        f"letter-spacing:.6px;text-transform:uppercase;margin-bottom:4px;'>"
        f"AltSpace</div>"
        f"<div style='color:#e7e9ee;font-size:14px;line-height:1.55;"
        f"white-space:pre-wrap;'>{_esc(message)}</div></div>",
        unsafe_allow_html=True,
    )


def summary_panel(summary: dict[str, Any]) -> None:
    """Render one EOD summary: date header + summary text + tomorrow's plan."""
    summary_date = summary.get("summary_date", "")
    pretty_date = _pretty_date(summary_date)
    summary_text = summary.get("summary_text") or "—"
    tomorrow_plan = summary.get("tomorrow_plan") or ""

    st.markdown(
        f"<div style='background:#1f232b;border-radius:8px;padding:12px 14px;"
        f"margin-bottom:10px;height:100%;'>"
        f"<div style='color:#f5a623;font-size:12px;font-weight:700;"
        f"margin-bottom:6px;'>{_esc(pretty_date)}</div>"
        f"<div style='color:#e7e9ee;font-size:13px;line-height:1.5;"
        f"white-space:pre-wrap;'>{_esc(summary_text)}</div>"
        + (
            f"<div style='margin-top:10px;padding-top:10px;"
            f"border-top:1px solid #2c3240;'>"
            f"<div style='color:#9aa0aa;font-size:11px;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px;'>"
            f"Tomorrow</div>"
            f"<div style='color:#c8ccd4;font-size:12px;line-height:1.5;"
            f"white-space:pre-wrap;'>{_esc(tomorrow_plan)}</div></div>"
            if tomorrow_plan
            else ""
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def review_panel(review: dict[str, Any]) -> None:
    """Render one weekly review: week-start header + the patterns paragraph."""
    week_start = review.get("week_start", "")
    pretty = _pretty_date(week_start)
    patterns = review.get("patterns_text") or "No patterns recorded yet."
    st.markdown(
        f"<div style='background:#1f232b;border-radius:8px;padding:14px 16px;"
        f"margin-bottom:12px;border-left:3px solid #f5a623;'>"
        f"<div style='color:#9aa0aa;font-size:12px;font-weight:700;"
        f"margin-bottom:6px;'>Week of {_esc(pretty)}</div>"
        f"<div style='color:#e7e9ee;font-size:14px;line-height:1.6;"
        f"white-space:pre-wrap;'>{_esc(patterns)}</div></div>",
        unsafe_allow_html=True,
    )


def streak_badge(streak: int) -> str:
    """Return an HTML streak badge for the sidebar."""
    flame = "🔥" if streak > 0 else "·"
    label = f"{streak}-day streak" if streak != 1 else "1-day streak"
    if streak <= 0:
        label = "No streak yet"
    return (
        f"<span style='display:inline-flex;align-items:center;gap:5px;"
        f"background:#1f232b;border:1px solid #2c3240;border-radius:14px;"
        f"padding:3px 10px;font-size:12px;color:#e7e9ee;'>"
        f"{flame} {_esc(label)}</span>"
    )


def _pretty_date(value: Any) -> str:
    d = _parse_date(value)
    if d is None:
        return str(value or "")
    return d.strftime("%a, %b %-d") if _supports_dash() else d.strftime("%a, %b %d")


def _supports_dash() -> bool:
    """``%-d`` (no leading zero) is POSIX-only; fall back to ``%d`` on Windows."""
    try:
        date.today().strftime("%-d")
        return True
    except ValueError:
        return False
