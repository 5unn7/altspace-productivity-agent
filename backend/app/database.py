"""Database engine, session factory, and FastAPI session dependency.

`Base` is re-exported from models so Alembic's env.py and any consumer can do
`from app.database import Base`. `get_db()` is the per-request Session
dependency every protected route depends on (directly or via get_current_user).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base  # re-exported for Alembic + consumers

__all__ = ["engine", "SessionLocal", "get_db", "init_db", "Base"]


def _engine_kwargs(url: str) -> dict:
    """SQLite needs check_same_thread off for FastAPI's threadpool; Postgres
    benefits from pre-ping to survive Render free-tier connection drops."""
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


engine = create_engine(settings.DATABASE_URL, **_engine_kwargs(settings.DATABASE_URL))

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session, guaranteed closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables from the ORM metadata.

    Dev convenience / deploy fallback so the app is usable even if Alembic
    migrations have not been run yet. Idempotent — only creates missing tables.
    """
    Base.metadata.create_all(bind=engine)
