"""initial schema — users, tasks, daily_logs, eod_summaries, weekly_reviews

Hand-written initial migration. Mirrors backend/app/models.py exactly so a
fresh deploy (`alembic upgrade head`) builds the full AltSpace schema on either
SQLite (dev) or Postgres (prod, Render).

Revision ID: 0001
Revises: (none — this is the base revision)
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users ----
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("streak_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_checkin_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ---- tasks ----
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column(
            "category", sa.String(length=20), nullable=False, server_default="other"
        ),
        sa.Column(
            "priority", sa.String(length=10), nullable=False, server_default="medium"
        ),
        sa.Column(
            "status", sa.String(length=12), nullable=False, server_default="pending"
        ),
        sa.Column(
            "source", sa.String(length=16), nullable=False, server_default="morning"
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"], unique=False)
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"], unique=False)

    # ---- daily_logs ----
    op.create_table(
        "daily_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_logs_user_id", "daily_logs", ["user_id"], unique=False)
    op.create_index("ix_daily_logs_log_date", "daily_logs", ["log_date"], unique=False)

    # ---- eod_summaries ----
    op.create_table(
        "eod_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("tomorrow_plan", sa.Text(), nullable=False, server_default=""),
        sa.Column("stats_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eod_summaries_user_id", "eod_summaries", ["user_id"], unique=False
    )
    op.create_index(
        "ix_eod_summaries_summary_date",
        "eod_summaries",
        ["summary_date"],
        unique=False,
    )

    # ---- weekly_reviews ----
    op.create_table(
        "weekly_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("patterns_text", sa.Text(), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_weekly_reviews_user_id", "weekly_reviews", ["user_id"], unique=False
    )
    op.create_index(
        "ix_weekly_reviews_week_start",
        "weekly_reviews",
        ["week_start"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in reverse FK order (children before parent `users`).
    op.drop_index("ix_weekly_reviews_week_start", table_name="weekly_reviews")
    op.drop_index("ix_weekly_reviews_user_id", table_name="weekly_reviews")
    op.drop_table("weekly_reviews")

    op.drop_index("ix_eod_summaries_summary_date", table_name="eod_summaries")
    op.drop_index("ix_eod_summaries_user_id", table_name="eod_summaries")
    op.drop_table("eod_summaries")

    op.drop_index("ix_daily_logs_log_date", table_name="daily_logs")
    op.drop_index("ix_daily_logs_user_id", table_name="daily_logs")
    op.drop_table("daily_logs")

    op.drop_index("ix_tasks_due_date", table_name="tasks")
    op.drop_index("ix_tasks_user_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
