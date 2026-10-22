"""business domain admin tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "business_domains" not in existing_tables:
        op.create_table(
            "business_domains",
            sa.Column("id", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("keywords", JSONB, nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("datasource_id", sa.String(length=128), nullable=True),
            sa.Column("schema_scope", JSONB, nullable=True),
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
            sa.ForeignKeyConstraint(
                ["datasource_id"],
                ["datasources.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_business_domains_sort_order_id",
            "business_domains",
            ["sort_order", "id"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            INSERT INTO business_domains
              (id, display_name, keywords, sort_order, datasource_id, schema_scope)
            VALUES
              ('finance', 'Finance', '["finance","invoice","ledger","budget","revenue"]'::jsonb, 10, NULL, NULL),
              ('hr', 'HR', '["employee","hr","payroll","staff","headcount"]'::jsonb, 20, NULL, NULL),
              ('general', 'General', '[]'::jsonb, 999, NULL, NULL)
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "business_domains" in existing_tables:
        op.drop_index("ix_business_domains_sort_order_id", table_name="business_domains")
        op.drop_table("business_domains")
