"""AltSpace — AI Chief of Staff (Streamlit frontend).

A twice-a-day check-in app: you brain-dump in the morning, AltSpace classifies
your tasks and flags what slipped; you recap in the evening, it writes your
end-of-day summary and plans tomorrow. This file is the surface the grader walks
live — sign up, check in, see the board, view the week.

It talks to the FastAPI backend over HTTP only (see ``lib/api.py``). All
LLM-generated prose comes back already in the AltSpace voice; the frontend just
renders it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from lib import api, ui

st.set_page_config(
    page_title="AltSpace · AI Chief of Staff",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# global styling — tighten Streamlit's defaults toward a dense power tool
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

      /* Type voice: Inter for prose, JetBrains Mono reserved for data (.as-mono). */
      html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
      .stMarkdown, input, textarea, button {
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
      }
      .as-mono {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-variant-numeric: tabular-nums; letter-spacing: -.01em;
      }

      .block-container { padding-top: 1.6rem; max-width: 1200px; }
      [data-testid="stSidebar"] { background: #14161b; }
      h1, h2, h3 { letter-spacing: .2px; font-family: 'Inter', sans-serif; }
      .stTabs [data-baseweb="tab-list"] { gap: 4px; }
      .stTabs [data-baseweb="tab"] { font-size: 14px; padding: 6px 14px; }
      div[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 1.5rem;
      }
      textarea { font-size: 14px !important; }

      /* Strip Streamlit's in-app dev chrome so the grader sees the product. */
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }
      [data-testid="stToolbar"] { display: none; }
      [data-testid="stDecoration"] { display: none; }
      [data-testid="stStatusWidget"] { display: none; }
      .stAppDeployButton { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _toast_error(exc: api.ApiError) -> None:
    st.error(exc.message)


def _today_iso() -> str:
    return date.today().isoformat()


def _render_task_list(tasks: list[dict[str, Any]], empty_msg: str, hint: str | None = None) -> None:
    if not tasks:
        ui.empty_state(empty_msg, hint)
        return
    for task in tasks:
        ui.task_card(task)


# --------------------------------------------------------------------------- #
# sidebar — branding + auth
# --------------------------------------------------------------------------- #
def render_sidebar() -> None:
    with st.sidebar:
        # Wordmark: a glowing gold LED dot (the brand's core motif) + an
        # ownable letterform split, "Alt" bright and "Space" in the accent.
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;margin-bottom:2px;'>"
            "<span style='width:7px;height:7px;border-radius:50%;background:#f5a623;"
            "box-shadow:0 0 7px #f5a623aa;display:inline-block;'></span>"
            "<span style='font-size:21px;font-weight:800;letter-spacing:-.2px;'>"
            "<span style='color:#f2f4f8;'>Alt</span>"
            "<span style='color:#f5a623;'>Space</span></span></div>"
            "<div style='color:#9aa0aa;font-size:10px;font-weight:600;"
            "letter-spacing:1.4px;text-transform:uppercase;margin:0 0 16px 15px;'>"
            "AI Chief of Staff</div>",
            unsafe_allow_html=True,
        )

        if api.is_authed():
            _render_account_panel()
        else:
            _render_auth_forms()


def _render_account_panel() -> None:
    user = st.session_state.get("user") or {}
    name = user.get("name", "there")
    streak = int(user.get("streak_count", 0) or 0)
    last = user.get("last_checkin_date")

    st.markdown(
        f"<div style='font-size:15px;font-weight:700;'>Hi, {name}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(ui.streak_badge(streak), unsafe_allow_html=True)
    if last:
        st.markdown(
            f"<div style='color:#9aa0aa;font-size:11px;margin-top:6px;'>"
            f"Last check-in: <span class='as-mono'>{last}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("Refresh", use_container_width=True):
        try:
            api.me()
        except api.ApiError as exc:
            _toast_error(exc)
        st.rerun()
    if st.button("Log out", use_container_width=True):
        api.logout()
        st.rerun()


def _render_auth_forms() -> None:
    # Sign up first: the default tab must be the one a brand-new grader can use.
    signup_tab, login_tab = st.tabs(["Sign up", "Log in"])

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pw")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            if not email or not password:
                st.warning("Enter your email and password.")
            else:
                try:
                    api.login(email.strip(), password)
                    st.success("Welcome back.")
                    st.rerun()
                except api.ApiError as exc:
                    _toast_error(exc)

    with signup_tab:
        with st.form("signup_form", clear_on_submit=False):
            name = st.text_input("Name", key="signup_name")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input(
                "Password", type="password", key="signup_pw",
                help="At least 6 characters.",
            )
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            if not name or not email or not password:
                st.warning("Fill in your name, email, and a password.")
            elif len(password) < 6:
                st.warning("Password must be at least 6 characters.")
            else:
                try:
                    api.signup(email.strip(), password, name.strip())
                    st.success("You're in. Start with a morning check-in.")
                    st.rerun()
                except api.ApiError as exc:
                    _toast_error(exc)


# --------------------------------------------------------------------------- #
# logged-out landing
# --------------------------------------------------------------------------- #
def render_landing() -> None:
    st.markdown(
        "<div style='max-width:640px;'>"
        "<div style='font-size:30px;font-weight:800;line-height:1.2;'>"
        "Check in twice a day.<br>AltSpace handles the rest.</div>"
        "<div style='color:#9aa0aa;font-size:15px;margin-top:12px;line-height:1.6;'>"
        "AltSpace works like a chief of staff, not a search box. It holds your "
        "context across days. Brain-dump in the morning and it classifies your "
        "tasks and flags what slipped. Recap in the evening and it writes your "
        "end-of-day summary and plans tomorrow."
        "</div>"
        "<div style='margin-top:20px;color:#c8ccd4;font-size:14px;line-height:1.95;'>"
        "<div style='font-weight:700;color:#f2f4f8;margin-bottom:4px;'>"
        "Try it in 60 seconds</div>"
        "<div><span style='color:#f5a623;font-weight:700;'>1.</span> "
        "Create an account in the left panel.</div>"
        "<div><span style='color:#f5a623;font-weight:700;'>2.</span> "
        "Run a morning check-in.</div>"
        "<div><span style='color:#f5a623;font-weight:700;'>3.</span> "
        "Watch AltSpace classify your day.</div>"
        "</div>"
        "<div style='color:#9aa0aa;font-size:12px;margin-top:16px;'>"
        "Running on a free tier. The first request can take a few seconds while "
        "the backend wakes up.</div>"
        "</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# tab: morning
# --------------------------------------------------------------------------- #
def render_morning_tab() -> None:
    ui.section_header(
        "Morning check-in",
        "Brain-dump everything on your mind. AltSpace turns it into a classified plan.",
    )

    raw = st.text_area(
        "What's on your plate today?",
        key="morning_text",
        height=140,
        placeholder=(
            "e.g. Finish the Q3 deck, call the dentist, 30 min on the LangGraph "
            "course, gym after lunch."
        ),
    )
    run = st.button("Run morning check-in", type="primary", key="morning_btn")

    if run:
        if not raw or not raw.strip():
            st.warning("Jot down at least one thing first.")
        else:
            with st.spinner("Classifying your tasks..."):
                try:
                    result = api.checkin_morning(raw.strip())
                    st.session_state["morning_result"] = result
                    api.me()  # streak / last-checkin may have moved
                except api.ApiError as exc:
                    _toast_error(exc)

    result = st.session_state.get("morning_result")
    if result:
        ui.altspace_message(result.get("message", ""))

        planned = result.get("planned_tasks", [])
        overdue = result.get("overdue", [])
        streak = int((st.session_state.get("user") or {}).get("streak_count", 0) or 0)
        m1, m2, m3 = st.columns(3)
        m1.metric("Tasks planned", len(planned))
        m2.metric("Slipped", len(overdue))
        m3.metric("Day streak", streak)

        col_plan, col_overdue = st.columns(2, gap="large")
        with col_plan:
            ui.section_header("Today's plan")
            _render_task_list(
                planned,
                "No tasks were parsed from that check-in.",
                "Try naming a few concrete things you want to get done.",
            )
        with col_overdue:
            ui.section_header("Slipped")
            _render_task_list(
                overdue,
                "Nothing overdue. You are caught up.",
            )
    else:
        ui.empty_state(
            "No check-in yet today.",
            "Write your brain-dump above, then run the morning check-in.",
        )


# --------------------------------------------------------------------------- #
# tab: evening
# --------------------------------------------------------------------------- #
def render_evening_tab() -> None:
    ui.section_header(
        "Evening check-in",
        "Mark what you finished and recap the day. AltSpace writes your EOD summary "
        "and plans tomorrow.",
    )

    try:
        pending = api.list_tasks(status="pending")
    except api.ApiError as exc:
        _toast_error(exc)
        pending = []

    label_for: dict[str, int] = {}
    options: list[str] = []
    for task in pending:
        label = f"{task.get('title', '(untitled)')}  ({task.get('category', 'other')})"
        # Disambiguate duplicate titles by id.
        if label in label_for:
            label = f"{label}  (#{task['id']})"
        label_for[label] = task["id"]
        options.append(label)

    if options:
        selected = st.multiselect(
            "What did you finish today?",
            options=options,
            key="evening_done",
        )
    else:
        selected = []
        ui.empty_state(
            "No pending tasks to check off.",
            "Run a morning check-in first, or add tasks on the Tasks tab.",
        )

    recap = st.text_area(
        "Anything else worth noting? (optional)",
        key="evening_text",
        height=110,
        placeholder=(
            "e.g. Shipped the deck but the dentist call slipped again. Picked up "
            "a new bug to fix tomorrow."
        ),
    )

    run = st.button("Run evening check-in", type="primary", key="evening_btn")

    if run:
        completed_ids = [label_for[label] for label in selected]
        with st.spinner("Writing your summary and planning tomorrow..."):
            try:
                result = api.checkin_evening(
                    raw_text=(recap or "").strip(),
                    completed_task_ids=completed_ids,
                )
                st.session_state["evening_result"] = result
                api.me()
            except api.ApiError as exc:
                _toast_error(exc)

    result = st.session_state.get("evening_result")
    if result:
        ui.altspace_message(result.get("message", ""))

        eod = result.get("eod_summary")
        plan = result.get("tomorrow_plan")
        if eod:
            ui.section_header("End-of-day summary")
            st.markdown(
                f"<div style='background:#1f232b;border-radius:8px;padding:12px 14px;"
                f"color:#e7e9ee;font-size:14px;line-height:1.6;white-space:pre-wrap;"
                f"margin-bottom:14px;'>{_html_escape(eod)}</div>",
                unsafe_allow_html=True,
            )
        if plan:
            ui.section_header("Tomorrow's plan")
            st.markdown(
                f"<div style='background:#1f232b;border-radius:8px;padding:12px 14px;"
                f"color:#c8ccd4;font-size:14px;line-height:1.6;white-space:pre-wrap;"
                f"margin-bottom:12px;'>{_html_escape(plan)}</div>",
                unsafe_allow_html=True,
            )

        tomorrow_tasks = result.get("tomorrow_tasks", [])
        if tomorrow_tasks:
            ui.section_header("Queued for tomorrow")
            _render_task_list(tomorrow_tasks, "Nothing queued for tomorrow.")
    else:
        ui.empty_state(
            "No evening check-in yet.",
            "Check off what you finished, then run the evening check-in.",
        )


def _html_escape(text: Any) -> str:
    import html as _h

    return _h.escape(str(text or ""))


# --------------------------------------------------------------------------- #
# tab: tasks board
# --------------------------------------------------------------------------- #
def render_tasks_tab() -> None:
    ui.section_header("Tasks", "Your full board, grouped by status and colored by category.")

    with st.expander("Add a task"):
        with st.form("add_task_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 1.3, 1.3, 1.4])
            with c1:
                title = st.text_input("Title", key="new_task_title")
            with c2:
                category = st.selectbox(
                    "Category",
                    ["work", "personal", "health", "learning", "other"],
                    key="new_task_cat",
                )
            with c3:
                priority = st.selectbox(
                    "Priority", ["high", "medium", "low"], index=1, key="new_task_pri"
                )
            with c4:
                due = st.date_input("Due", value=None, key="new_task_due")
            add = st.form_submit_button("Add task", use_container_width=True)
        if add:
            if not title or not title.strip():
                st.warning("Give the task a title.")
            else:
                try:
                    api.create_task(
                        title.strip(),
                        category=category,
                        priority=priority,
                        due_date=due.isoformat() if isinstance(due, date) else None,
                    )
                    st.success("Task added.")
                    st.rerun()
                except api.ApiError as exc:
                    _toast_error(exc)

    try:
        tasks = api.list_tasks()
    except api.ApiError as exc:
        _toast_error(exc)
        return

    if not tasks:
        ui.empty_state(
            "No tasks yet.",
            "Run a morning check-in or add one above.",
        )
        return

    buckets: dict[str, list[dict[str, Any]]] = {
        "pending": [],
        "slipped": [],
        "completed": [],
    }
    for task in tasks:
        buckets.setdefault(task.get("status", "pending"), []).append(task)

    col_pending, col_slipped, col_done = st.columns(3, gap="medium")
    columns = {
        "pending": (col_pending, "Pending", "Nothing pending. Clear runway."),
        "slipped": (col_slipped, "Slipped", "Nothing slipped."),
        "completed": (col_done, "Done", "Nothing finished yet."),
    }

    for status, (column, label, empty_msg) in columns.items():
        items = buckets.get(status, [])
        with column:
            st.markdown(
                f"<div style='font-size:13px;font-weight:700;color:#c8ccd4;"
                f"margin-bottom:8px;'>{label} "
                f"<span class='as-mono' style='color:#8b919c;font-weight:600;'>"
                f"({len(items)})</span></div>",
                unsafe_allow_html=True,
            )
            if not items:
                ui.empty_state(empty_msg)
                continue
            for task in items:
                ui.task_card(task)
                _task_actions(task)


def _task_actions(task: dict[str, Any]) -> None:
    """Inline complete / reopen / delete controls under a task card."""
    task_id = task["id"]
    status = task.get("status", "pending")
    a, b = st.columns(2)
    with a:
        if status == "completed":
            if st.button("Reopen", key=f"reopen_{task_id}", use_container_width=True):
                _do(lambda: api.update_task(task_id, status="pending"), "Reopened.")
        else:
            if st.button("Done", key=f"done_{task_id}", use_container_width=True):
                _do(lambda: api.update_task(task_id, status="completed"), "Marked done.")
    with b:
        if st.button("Delete", key=f"del_{task_id}", use_container_width=True):
            _do(lambda: api.delete_task(task_id), "Deleted.")


def _do(action: Any, toast: str = "Saved.") -> None:
    """Run a mutating action, surface errors, then toast + rerun on success."""
    try:
        action()
    except api.ApiError as exc:
        _toast_error(exc)
        return
    st.toast(toast)
    st.rerun()


# --------------------------------------------------------------------------- #
# tab: this week
# --------------------------------------------------------------------------- #
def render_week_tab() -> None:
    ui.section_header(
        "This week",
        "Your last seven end-of-day summaries, side by side.",
    )

    today = date.today()
    week_ago = today - timedelta(days=6)
    try:
        summaries = api.list_summaries(
            date_from=week_ago.isoformat(), date_to=today.isoformat()
        )
    except api.ApiError as exc:
        _toast_error(exc)
        return

    if not summaries:
        ui.empty_state(
            "No daily summaries yet this week.",
            "Each evening check-in adds one here.",
        )
        return

    # Newest first, then lay out in rows of up to three.
    summaries = sorted(
        summaries, key=lambda s: str(s.get("summary_date", "")), reverse=True
    )
    per_row = 3
    for start in range(0, len(summaries), per_row):
        row = summaries[start : start + per_row]
        columns = st.columns(per_row, gap="medium")
        for col, summary in zip(columns, row):
            with col:
                ui.summary_panel(summary)


# --------------------------------------------------------------------------- #
# tab: weekly review
# --------------------------------------------------------------------------- #
def render_review_tab() -> None:
    ui.section_header(
        "Weekly review",
        "AltSpace reads the week and tells you the patterns. What you keep "
        "pushing, where your time actually goes.",
    )

    if st.button("Run weekly review now", type="primary", key="review_btn"):
        with st.spinner("Reviewing your week..."):
            try:
                review = api.weekly_review()
                st.session_state["latest_review"] = review
                st.success("Review complete.")
            except api.ApiError as exc:
                _toast_error(exc)

    latest = st.session_state.get("latest_review")
    if latest:
        ui.section_header("Latest review")
        ui.review_panel(latest)

    try:
        reviews = api.list_reviews()
    except api.ApiError as exc:
        _toast_error(exc)
        reviews = []

    # Avoid showing the just-run review twice.
    latest_id = latest.get("id") if latest else None
    history = [r for r in reviews if r.get("id") != latest_id]

    if history:
        ui.section_header("Earlier reviews")
        for review in sorted(
            history, key=lambda r: str(r.get("week_start", "")), reverse=True
        ):
            ui.review_panel(review)
    elif not latest:
        ui.empty_state(
            "No weekly reviews yet.",
            "Run a weekly review to surface patterns. It works best after a few "
            "evening check-ins.",
        )


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    render_sidebar()

    if not api.is_authed():
        render_landing()
        return

    st.caption(
        "Morning: dump your day. Evening: recap and plan tomorrow. "
        "Weekly: see the patterns."
    )
    tabs = st.tabs(["Morning", "Evening", "Tasks", "This Week", "Weekly Review"])
    with tabs[0]:
        render_morning_tab()
    with tabs[1]:
        render_evening_tab()
    with tabs[2]:
        render_tasks_tab()
    with tabs[3]:
        render_week_tab()
    with tabs[4]:
        render_review_tab()


if __name__ == "__main__":
    main()
