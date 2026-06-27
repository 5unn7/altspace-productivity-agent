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
# AltSpace's dual-accent system. Gold is the ONE true accent (the agent itself,
# and "needs attention now"). Every other color means exactly one thing, and no
# color is ever reused for two meanings. No purple, anywhere.
#
# Locked semantic set:
GOLD = "#f5a623"     # AltSpace / active / due-today / medium priority
DONE = "#57c98a"     # completed, and only completed
ALERT = "#f26d65"    # overdue / slipped / high priority (AA-safe as 11px pill text)
MUTED = "#9aa0aa"    # labels + secondary text (passes AA on every surface)
GHOST = "#8b919c"    # low priority / "no due date" (lifted from #6b7280 for AA)
NEUTRAL = "#c8ccd4"  # near-term but not urgent (e.g. due tomorrow)

# Surface ladder — surfaces separate by background step, not borders.
SURFACE_1 = "#1a1d24"  # empty states / the step above app-bg
SURFACE_2 = "#1f232b"  # cards, panels, inputs

# Category tints — quiet wayfinding only (left stripe + LED dot). Each is
# distinct from the semantic set and from the others. Violet is gone; health is
# sage (not the done-green); learning is teal (not the gold accent).
CATEGORY_COLORS: dict[str, str] = {
    "work": "#5b9bd5",      # steel blue
    "personal": "#d98a6a",  # clay (was AI-violet #c084e8)
    "health": "#6f9f7f",    # sage (was the done-green)
    "learning": "#5fa0a8",  # muted teal (was the gold accent)
    "other": "#8a8f99",     # neutral grey
}

PRIORITY_COLORS: dict[str, str] = {
    "high": ALERT,
    "medium": GOLD,
    "low": GHOST,
}

STATUS_COLORS: dict[str, str] = {
    "pending": MUTED,
    "completed": DONE,
    "slipped": ALERT,
}

STATUS_LABELS: dict[str, str] = {
    "pending": "Pending",
    "completed": "Done",
    "slipped": "Slipped",
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
    """Return (text, color) describing a due date relative to today.

    Urgency lives entirely in the locked semantic ladder (red, gold, neutral,
    muted), so a due-date pill never shares a color with a content category.
    """
    due = _parse_date(due_value)
    if due is None:
        return ("No due date", GHOST)
    delta = (due - date.today()).days
    if delta < 0:
        n = abs(delta)
        return (f"Overdue {n}d", ALERT)
    if delta == 0:
        return ("Due today", GOLD)
    if delta == 1:
        return ("Due tomorrow", NEUTRAL)
    return (f"Due in {delta}d", MUTED)


# Mono face for any pill that carries data (dates), reinforcing "mono for data".
_MONO = "font-family:'JetBrains Mono',ui-monospace,monospace;"


def _pill(text: str, color: str, *, filled: bool = False, mono: bool = False) -> str:
    font = _MONO if mono else ""
    if filled:
        return (
            f"<span style='display:inline-block;padding:1px 8px;border-radius:10px;"
            f"background:{color};color:#0e0f12;font-size:11px;font-weight:600;"
            f"line-height:18px;{font}'>{_esc(text)}</span>"
        )
    return (
        f"<span style='display:inline-block;padding:1px 8px;border-radius:10px;"
        f"border:1px solid {color};color:{color};font-size:11px;font-weight:600;"
        f"line-height:18px;{font}'>{_esc(text)}</span>"
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
    status_color = STATUS_COLORS.get(status, MUTED)

    due_text, due_color = _due_label(task.get("due_date"))
    completed = status == "completed"
    title_style = (
        f"text-decoration:line-through;color:{MUTED};"
        if completed
        else "color:#e7e9ee;"
    )

    badges = [
        _pill(priority.upper(), pri_color),
        _pill(STATUS_LABELS.get(status, status), status_color),
        _pill(due_text, due_color, mono=True),
    ]
    if source == "agent_planned":
        badges.append(_pill("AltSpace", GOLD, filled=True))
    elif source == "emerged":
        badges.append(_pill("Emerged", "#8a8f99"))

    badge_html = "&nbsp;".join(badges)

    # The category color rides the left stripe + a single LED dot; the category
    # word stays muted grey so gold remains the only true accent on the card.
    st.markdown(
        f"<div style='display:flex;gap:10px;align-items:flex-start;"
        f"background:{SURFACE_2};border-left:3px solid {cat_color};"
        f"border-radius:8px;padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='color:{cat_color};font-size:10px;line-height:22px;'>●</div>"
        f"<div style='flex:1;min-width:0;'>"
        f"<div style='font-size:14px;font-weight:600;{title_style}"
        f"word-break:break-word;'>{_esc(title)}</div>"
        f"<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;"
        f"align-items:center;'>"
        f"<span style='color:{MUTED};font-size:11px;font-weight:600;"
        f"letter-spacing:.2px;'>{_esc(category.capitalize())}</span>"
        f"{badge_html}</div></div></div>",
        unsafe_allow_html=True,
    )


def empty_state(message: str, hint: str | None = None) -> None:
    """Honest empty state, no fake data, just a calm nudge.

    Separates from the page by a background step (SURFACE_1) rather than a
    dashed border, and keeps hint text at an AA-passing grey.
    """
    hint_html = (
        f"<div style='color:{MUTED};font-size:12px;margin-top:4px;'>{_esc(hint)}</div>"
        if hint
        else ""
    )
    st.markdown(
        f"<div style='background:{SURFACE_1};border-radius:8px;"
        f"padding:18px;text-align:center;color:{MUTED};font-size:13px;'>"
        f"{_esc(message)}{hint_html}</div>",
        unsafe_allow_html=True,
    )


def altspace_message(message: str) -> None:
    """Render an AltSpace-voice paragraph in a distinct, branded panel.

    The only border is the meaningful 3px gold left-stripe (the brand accent);
    the surface itself separates by background, not an outline.
    """
    if not message:
        return
    st.markdown(
        f"<div style='background:#1b1f27;"
        f"border-left:3px solid {GOLD};border-radius:8px;padding:12px 14px;"
        f"margin:6px 0 12px 0;'>"
        f"<div style='color:{GOLD};font-size:11px;font-weight:700;"
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
    summary_text = summary.get("summary_text") or "No summary recorded for this day."
    tomorrow_plan = summary.get("tomorrow_plan") or ""

    st.markdown(
        f"<div style='background:{SURFACE_2};border-radius:8px;padding:12px 14px;"
        f"margin-bottom:10px;height:100%;'>"
        f"<div style='color:{GOLD};font-size:12px;font-weight:700;"
        f"margin-bottom:6px;{_MONO}'>{_esc(pretty_date)}</div>"
        f"<div style='color:#e7e9ee;font-size:13px;line-height:1.5;"
        f"white-space:pre-wrap;'>{_esc(summary_text)}</div>"
        + (
            f"<div style='margin-top:10px;padding-top:10px;"
            f"border-top:1px solid #2c3240;'>"
            f"<div style='color:{MUTED};font-size:11px;font-weight:700;"
            f"margin-bottom:3px;'>Tomorrow</div>"
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
        f"<div style='background:{SURFACE_2};border-radius:8px;padding:14px 16px;"
        f"margin-bottom:12px;border-left:3px solid {GOLD};'>"
        f"<div style='color:{MUTED};font-size:12px;font-weight:700;margin-bottom:6px;'>"
        f"Week of <span style='{_MONO}'>{_esc(pretty)}</span></div>"
        f"<div style='color:#e7e9ee;font-size:14px;line-height:1.6;"
        f"white-space:pre-wrap;'>{_esc(patterns)}</div></div>",
        unsafe_allow_html=True,
    )


def streak_badge(streak: int) -> str:
    """Return an HTML streak badge for the sidebar (the number reads as data).

    Zero state shows no glyph (no orphan decorative dot); an active streak keeps
    the flame and renders the count in the mono face.
    """
    if streak <= 0:
        inner = "No streak yet"
    else:
        unit = "day" if streak == 1 else "days"
        inner = (
            f"🔥 <span style='{_MONO}font-weight:600;'>{streak}</span> {unit} streak"
        )
    return (
        f"<span style='display:inline-flex;align-items:center;gap:5px;"
        f"background:{SURFACE_2};border-radius:14px;"
        f"padding:3px 10px;font-size:12px;color:#e7e9ee;'>{inner}</span>"
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
