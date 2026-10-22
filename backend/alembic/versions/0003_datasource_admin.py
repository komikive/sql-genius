"""datasource admin tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "datasources" not in existing_tables:
        op.create_table(
            "datasources",
            sa.Column("id", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("dialect", sa.String(length=32), nullable=False),
            sa.Column("connection_url", sa.Text(), nullable=False),
            sa.Column(
                "is_default",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "dialect IN ('mysql', 'postgresql')",
                name="datasources_dialect_check",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "datasource_schema_snapshots" not in existing_tables:
        op.create_table(
            "datasource_schema_snapshots",
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("payload", JSONB, nullable=False),
            sa.Column(
                "captured_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["datasource_id"],
                ["datasources.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("datasource_id"),
        )


def downgrade() -> None:
    op.drop_table("datasource_schema_snapshots")
    op.drop_table("datasources")
