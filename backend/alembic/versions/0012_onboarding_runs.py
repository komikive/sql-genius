"""add onboarding_runs table

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "onboarding_runs" not in inspector.get_table_names():
        op.create_table(
            "onboarding_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "datasource_id",
                sa.String(length=255),
                sa.ForeignKey("datasources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("phase", sa.String(length=64), nullable=False, server_default="queued"),
            sa.Column("status_message", sa.Text, nullable=False, server_default=""),
            sa.Column("error", sa.Text, nullable=True),
            sa.Column("events", sa.JSON(), nullable=True),
            sa.Column("result_payload", sa.JSON(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    existing_indexes = {item["name"] for item in inspector.get_indexes("onboarding_runs")}
    if "ix_onboarding_runs_datasource_id" not in existing_indexes:
        op.create_index("ix_onboarding_runs_datasource_id", "onboarding_runs", ["datasource_id"])
    if "ix_onboarding_runs_status" not in existing_indexes:
        op.create_index("ix_onboarding_runs_status", "onboarding_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_runs_status", table_name="onboarding_runs")
    op.drop_index("ix_onboarding_runs_datasource_id", table_name="onboarding_runs")
    op.drop_table("onboarding_runs")
