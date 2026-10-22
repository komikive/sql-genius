"""history audit

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "admin_sessions" not in existing_tables:
        op.create_table(
            "admin_sessions",
            sa.Column("thread_id", sa.String(length=128), nullable=False),
            sa.Column("first_user_message", sa.Text(), nullable=True),
            sa.Column("last_user_message", sa.Text(), nullable=True),
            sa.Column("latest_domain_id", sa.String(length=128), nullable=True),
            sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "last_activity_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("thread_id"),
        )
        op.create_index(
            "ix_admin_sessions_last_activity_at",
            "admin_sessions",
            ["last_activity_at"],
            unique=False,
        )

    if "sql_execution_history" not in existing_tables:
        op.create_table(
            "sql_execution_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("datasource_id", sa.String(length=128), nullable=True),
            sa.Column("sql_text", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("rowcount", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column(
                "executed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('success', 'failed')",
                name="ck_sql_execution_history_status",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_sql_execution_history_executed_at",
            "sql_execution_history",
            ["executed_at"],
            unique=False,
        )
        op.create_index(
            "ix_sql_execution_history_status",
            "sql_execution_history",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_sql_execution_history_thread_id",
            "sql_execution_history",
            ["thread_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sql_execution_history" in existing_tables:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("sql_execution_history")
        }
        if "ix_sql_execution_history_thread_id" in existing_indexes:
            op.drop_index(
                "ix_sql_execution_history_thread_id",
                table_name="sql_execution_history",
            )
        if "ix_sql_execution_history_status" in existing_indexes:
            op.drop_index(
                "ix_sql_execution_history_status",
                table_name="sql_execution_history",
            )
        if "ix_sql_execution_history_executed_at" in existing_indexes:
            op.drop_index(
                "ix_sql_execution_history_executed_at",
                table_name="sql_execution_history",
            )
        op.drop_table("sql_execution_history")

    if "admin_sessions" in existing_tables:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("admin_sessions")
        }
        if "ix_admin_sessions_last_activity_at" in existing_indexes:
            op.drop_index("ix_admin_sessions_last_activity_at", table_name="admin_sessions")
        op.drop_table("admin_sessions")
