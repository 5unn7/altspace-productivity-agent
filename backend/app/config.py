"""Application settings — pydantic-settings reading from environment / .env.

Every other module imports the singleton `settings` from here. Defaults are
dev-safe (SQLite, the two free Groq models) so the app boots with zero config;
prod overrides DATABASE_URL / GROQ_API_KEY / JWT_SECRET via real env vars.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- database ----
    # dev: SQLite file (zero setup). prod (Render): postgresql://...
    DATABASE_URL: str = "sqlite:///./altspace.db"

    # ---- auth (JWT) ----
    JWT_SECRET: str = "dev-insecure-secret-change-me-in-prod-please-32chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # ---- LLM: Groq free tier ----
    GROQ_API_KEY: str = ""
    CLASSIFIER_MODEL: str = "llama-3.1-8b-instant"
    SUMMARY_MODEL: str = "llama-3.3-70b-versatile"

    # ---- CORS: where the Streamlit frontend is served from ----
    FRONTEND_ORIGIN: str = "http://localhost:8501"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        """Render's managed Postgres emits a ``postgres://`` URL, but SQLAlchemy 2.0
        + psycopg2 require the ``postgresql://`` scheme. Normalize once here so every
        consumer (engine, Alembic env.py, the LangGraph checkpointer) gets a working
        URL — this is the single point of truth the render.yaml comment refers to."""
        if v.startswith("postgres://"):
            return "postgresql://" + v[len("postgres://") :]
        return v


settings = Settings()
