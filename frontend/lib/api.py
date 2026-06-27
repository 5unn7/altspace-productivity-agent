"""HTTP client for the AltSpace backend.

This module is the *only* place the frontend talks to the backend. It speaks
plain HTTP per BUILD-PLAN §4 — no backend imports, no shared code. The JWT lives
in ``st.session_state`` once a user logs in; every authed call attaches it as
``Authorization: Bearer <token>``.

Base URL resolution order:
  1. ``st.secrets["API_BASE_URL"]`` (Streamlit Community Cloud deploy)
  2. ``API_BASE_URL`` environment variable (local / Render-paired)
  3. ``http://localhost:8000`` (default for local dev)

Every function returns parsed JSON (dict / list) on success and raises
``ApiError`` on failure, with a human-readable ``message`` the UI can show
without leaking stack traces or 500s onto the screen.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

DEFAULT_BASE_URL = "http://localhost:8000"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)  # LLM calls can be slow; be patient.


class ApiError(Exception):
    """A backend call failed. ``message`` is safe to show the user."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# --------------------------------------------------------------------------- #
# base url + headers
# --------------------------------------------------------------------------- #
def base_url() -> str:
    """Resolve the backend base URL (secrets → env → localhost), no trailing slash.

    Defensively strips a trailing ``/docs`` / ``/openapi.json`` / ``/redoc`` —
    the backend's Swagger URL is the easiest thing to paste into the
    ``API_BASE_URL`` secret by mistake, and ``{base}/docs/auth/signup`` 404s the
    whole app. Normalizing it here means the app keeps working even if the
    secret points at the docs page instead of the API root.
    """
    url: str | None = None
    try:
        # st.secrets raises if no secrets file exists; guard it.
        if "API_BASE_URL" in st.secrets:
            url = str(st.secrets["API_BASE_URL"])
    except Exception:
        url = None
    if not url:
        url = os.environ.get("API_BASE_URL") or DEFAULT_BASE_URL
    url = url.strip().rstrip("/")
    for suffix in ("/docs", "/openapi.json", "/redoc"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _token() -> str | None:
    return st.session_state.get("token")


def is_authed() -> bool:
    return bool(_token())


def _auth_headers() -> dict[str, str]:
    token = _token()
    if not token:
        raise ApiError("You're signed out. Log in again to continue.", 401)
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# low-level request helper
# --------------------------------------------------------------------------- #
def _detail_from_response(resp: httpx.Response) -> str:
    """Pull a clean error message out of a FastAPI error response."""
    try:
        body = resp.json()
    except Exception:
        return resp.text.strip() or f"Request failed ({resp.status_code})."

    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        # Pydantic validation errors: surface the first one readably.
        first = detail[0]
        if isinstance(first, dict):
            loc = first.get("loc", [])
            field = loc[-1] if loc else "input"
            msg = first.get("msg", "is invalid")
            return f"{field}: {msg}"
    return f"Request failed ({resp.status_code})."


def _request(
    method: str,
    path: str,
    *,
    auth: bool = True,
    json: Any | None = None,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """Perform a request, returning parsed JSON (or None for 204).

    Raises ``ApiError`` on transport failure or any non-2xx status.
    """
    headers: dict[str, str] = {}
    if auth:
        headers.update(_auth_headers())

    url = f"{base_url()}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.request(
                method,
                url,
                headers=headers,
                json=json,
                data=data,
                params=params,
            )
    except httpx.ConnectError:
        raise ApiError(
            f"Can't reach AltSpace at {base_url()}. Is the backend running?"
        ) from None
    except httpx.TimeoutException:
        raise ApiError(
            "AltSpace took too long to respond. The model may be warming up. "
            "Try again in a moment."
        ) from None
    except httpx.HTTPError as exc:  # pragma: no cover - defensive
        raise ApiError(f"Network error talking to AltSpace: {exc}") from None

    if resp.status_code == 401:
        # Token expired or missing — drop it so the UI shows the login screen.
        st.session_state.pop("token", None)
        st.session_state.pop("user", None)
        raise ApiError("Your session expired. Please log in again.", 401)

    if resp.status_code >= 400:
        raise ApiError(_detail_from_response(resp), resp.status_code)

    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def signup(email: str, password: str, name: str) -> dict[str, Any]:
    """Create an account; stores the returned token and loads the profile."""
    token = _request(
        "POST",
        "/auth/signup",
        auth=False,
        json={"email": email, "password": password, "name": name},
    )
    _store_token(token)
    return me()


def login(email: str, password: str) -> dict[str, Any]:
    """Log in and store the JWT.

    Prefers the JSON endpoint ``/auth/login-json``. If the backend only exposes
    the OAuth2 form login (``/auth/login`` with username/password), a 404/405/422
    triggers a fallback to the form-encoded shape — so this client works against
    either auth implementation.
    """
    token: Any | None = None
    try:
        token = _request(
            "POST",
            "/auth/login-json",
            auth=False,
            json={"email": email, "password": password},
        )
    except ApiError as exc:
        # 401 = wrong credentials: a retry won't help, re-raise.
        # 404/405/422 = wrong shape/endpoint: fall back to the form login.
        if exc.status_code in (404, 405, 422):
            token = _request(
                "POST",
                "/auth/login",
                auth=False,
                data={"username": email, "password": password},
            )
        else:
            raise

    _store_token(token)
    return me()


def _store_token(token: Any) -> None:
    if not isinstance(token, dict) or "access_token" not in token:
        raise ApiError("AltSpace returned an unexpected login response.")
    st.session_state["token"] = token["access_token"]


def me() -> dict[str, Any]:
    """Fetch the current user's profile and cache it in session state."""
    user = _request("GET", "/auth/me")
    st.session_state["user"] = user
    return user


def logout() -> None:
    for key in ("token", "user"):
        st.session_state.pop(key, None)


# --------------------------------------------------------------------------- #
# tasks
# --------------------------------------------------------------------------- #
def list_tasks(
    status: str | None = None, due_date: str | None = None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    if due_date:
        params["date"] = due_date
    result = _request("GET", "/tasks", params=params or None)
    return result or []


def create_task(
    title: str,
    category: str = "other",
    priority: str = "medium",
    due_date: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": title,
        "category": category,
        "priority": priority,
    }
    if due_date:
        body["due_date"] = due_date
    return _request("POST", "/tasks", json=body)


def update_task(task_id: int, **fields: Any) -> dict[str, Any]:
    """Patch a task. Only the provided fields are sent."""
    payload = {k: v for k, v in fields.items() if v is not None}
    return _request("PATCH", f"/tasks/{task_id}", json=payload)


def delete_task(task_id: int) -> None:
    _request("DELETE", f"/tasks/{task_id}")


# --------------------------------------------------------------------------- #
# check-ins
# --------------------------------------------------------------------------- #
def checkin_morning(raw_text: str) -> dict[str, Any]:
    return _request(
        "POST", "/checkin/morning", json={"raw_text": raw_text}
    )


def checkin_evening(
    raw_text: str = "", completed_task_ids: list[int] | None = None
) -> dict[str, Any]:
    return _request(
        "POST",
        "/checkin/evening",
        json={
            "raw_text": raw_text,
            "completed_task_ids": completed_task_ids or [],
        },
    )


# --------------------------------------------------------------------------- #
# review + summaries
# --------------------------------------------------------------------------- #
def weekly_review() -> dict[str, Any]:
    """Trigger the weekly pattern review now (same code APScheduler runs)."""
    return _request("POST", "/review/weekly")


def list_summaries(
    date_from: str | None = None, date_to: str | None = None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    result = _request("GET", "/summaries", params=params or None)
    return result or []


def list_reviews() -> list[dict[str, Any]]:
    result = _request("GET", "/reviews")
    return result or []
