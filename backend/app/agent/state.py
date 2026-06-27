"""LangGraph agent state — the contract between graph nodes.

One rolling thread per user (thread_id = f"user-{user_id}") so the checkpointer
carries state forward across days. Nodes read/write this TypedDict.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class ParsedTask(TypedDict, total=False):
    title: str
    category: str  # work | personal | health | learning | other
    priority: str  # low | medium | high
    due_date: str | None  # ISO date string or None


class CheckinState(TypedDict, total=False):
    # ---- inputs ----
    user_id: int
    kind: Literal["morning", "evening", "weekly"]
    raw_text: str
    completed_task_ids: list[int]

    # ---- working / outputs ----
    parsed_tasks: list[ParsedTask]
    overdue: list[dict]          # serialized TaskOut-like dicts
    eod_summary: str
    tomorrow_plan: str
    tomorrow_tasks: list[ParsedTask]
    patterns_text: str
    result_message: str          # the AltSpace-voice paragraph
