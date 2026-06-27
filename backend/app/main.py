"""FastAPI application entrypoint.

Wires CORS, a health route, DB init on startup, and the four feature routers
(auth, tasks, checkin, review). Router modules are written by the Modules stage;
each include is wrapped defensively so the app still boots (and `/docs` loads)
while a module is still being built — a downstream agent can run a smoke test
against this app without waiting for every router to land.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db

logger = logging.getLogger("altspace")

app = FastAPI(
    title="AltSpace API",
    description="AltSpace — your AI chief of staff. Check in twice a day; it "
    "remembers everything, surfaces what slipped, writes your EOD summary, "
    "and plans tomorrow.",
    version="0.1.0",
)

# ---- CORS ----
# Allow the configured Streamlit origin, plus "*" for dev convenience. Streamlit
# Cloud assigns the frontend origin; FRONTEND_ORIGIN pins it in prod.
_allowed_origins = list({settings.FRONTEND_ORIGIN, "*"})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    """Create tables if they don't exist (dev convenience / deploy fallback)."""
    init_db()


@app.get("/", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe — used by Render and the incognito smoke test."""
    return {"status": "ok"}


def _include_router(module_name: str, attr: str = "router") -> None:
    """Include a feature router, tolerating a not-yet-written module.

    During parallel build the route modules land at different times. A missing
    module logs a warning instead of crashing app import, so `/docs` and the
    health route stay available for downstream smoke testing.
    """
    try:
        module = __import__(f"app.routes.{module_name}", fromlist=[attr])
        app.include_router(getattr(module, attr))
        logger.info("Mounted router: app.routes.%s", module_name)
    except Exception as exc:  # noqa: BLE001 — boot-resilience is intentional here
        logger.warning("Router app.routes.%s not mounted yet: %s", module_name, exc)


for _name in ("auth", "tasks", "checkin", "review"):
    _include_router(_name)
