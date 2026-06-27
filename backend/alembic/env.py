"""Alembic migration environment.

Pulls the database URL from app.config.settings (so dev SQLite / prod Postgres
share one migration set) and points target_metadata at the ORM Base metadata so
`alembic revision --autogenerate` sees every model in app/models.py.

Run from the backend/ directory:
    alembic revision --autogenerate -m "init"
    alembic upgrade head
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable when alembic runs from the backend/ directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402  (Base re-exported from models)
import app.models  # noqa: E402,F401  (import for side effect: register all tables)

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Override the placeholder URL with the real one from settings.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configure Python logging from alembic.ini, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate target: all tables registered on Base.metadata.
target_metadata = Base.metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Run migrations without a live DBAPI connection (emits SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # batch mode lets ALTER work on SQLite (no native ALTER COLUMN)
        render_as_batch=_is_sqlite(url or ""),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=_is_sqlite(
                config.get_main_option("sqlalchemy.url") or ""
            ),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
