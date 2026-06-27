"""Groq LLM client factories + a robust JSON-from-reply helper.

Two tiers (per the build plan):
  - classifier_llm()  — small/fast model for parsing free text into structured tasks
  - summary_llm()     — larger model for EOD summaries, tomorrow plans, weekly patterns

chat_json(llm, system, user) sends a system+user message pair and returns a dict
parsed out of the reply. It is defensive on purpose: free-tier models sometimes
wrap JSON in code fences or add prose. We strip fences, slice to the outermost
{...}, and fall back to {} so the agent never 500s on a malformed reply.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.config import settings

__all__ = ["classifier_llm", "summary_llm", "chat_json"]


def classifier_llm(temperature: float = 0.0) -> ChatGroq:
    """Fast, cheap model for classification / parsing. Deterministic by default."""
    return ChatGroq(
        model=settings.CLASSIFIER_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=temperature,
    )


def summary_llm(temperature: float = 0.3) -> ChatGroq:
    """Larger model for summaries / plans / patterns. A little warmth for voice."""
    return ChatGroq(
        model=settings.SUMMARY_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=temperature,
    )


# A fenced ```json ... ``` (or bare ``` ... ```) block, captured loosely.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_text(reply: Any) -> str:
    """Pull plain text out of a LangChain message / string / content-blocks list."""
    content = getattr(reply, "content", reply)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts)
    return str(content)


def _parse_json_object(text: str) -> dict:
    """Best-effort: return the first JSON object found in `text`, else {}."""
    if not text:
        return {}

    # 1) try the whole thing
    stripped = text.strip()
    try:
        loaded = json.loads(stripped)
        return loaded if isinstance(loaded, dict) else {}
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) try the contents of a code fence
    fence = _FENCE_RE.search(text)
    if fence:
        inner = fence.group(1).strip()
        try:
            loaded = json.loads(inner)
            if isinstance(loaded, dict):
                return loaded
        except (json.JSONDecodeError, ValueError):
            pass

    # 3) slice to the outermost {...} and try that
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except (json.JSONDecodeError, ValueError):
            pass

    # 4) give up gracefully
    return {}


def chat_json(llm: ChatGroq, system: str, user: str) -> dict:
    """Call the model with a system+user prompt and return a parsed JSON object.

    Never raises on a malformed model reply — returns {} so callers can apply
    their own defaults. Genuine transport/auth errors (e.g. missing API key)
    still propagate so they surface loudly in dev.
    """
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    reply = llm.invoke(messages)
    return _parse_json_object(_extract_text(reply))
