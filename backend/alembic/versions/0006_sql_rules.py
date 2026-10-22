"""sql rules

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sql_rules" not in existing_tables:
        op.create_table(
            "sql_rules",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("scope_type", sa.String(length=32), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=True),
            sa.Column("domain_id", sa.String(length=128), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
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
                "scope_type IN ('global', 'datasource', 'domain')",
                name="ck_sql_rules_scope_type",
            ),
            sa.CheckConstraint(
                "("
                "(scope_type = 'global' AND datasource_id IS NULL AND domain_id IS NULL)"
                " OR "
                "(scope_type = 'datasource' AND datasource_id IS NOT NULL AND domain_id IS NULL)"
                " OR "
                "(scope_type = 'domain' AND datasource_id IS NULL AND domain_id IS NOT NULL)"
                ")",
                name="ck_sql_rules_scope_binding",
            ),
            sa.ForeignKeyConstraint(
                ["datasource_id"],
                ["datasources.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["domain_id"],
                ["business_domains.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sql_rules_scope_type", "sql_rules", ["scope_type"], unique=False)
        op.create_index(
            "ix_sql_rules_datasource_id", "sql_rules", ["datasource_id"], unique=False
        )
        op.create_index("ix_sql_rules_domain_id", "sql_rules", ["domain_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "sql_rules" in existing_tables:
        existing_indexes = {index["name"] for index in inspector.get_indexes("sql_rules")}
        if "ix_sql_rules_domain_id" in existing_indexes:
            op.drop_index("ix_sql_rules_domain_id", table_name="sql_rules")
        if "ix_sql_rules_datasource_id" in existing_indexes:
            op.drop_index("ix_sql_rules_datasource_id", table_name="sql_rules")
        if "ix_sql_rules_scope_type" in existing_indexes:
            op.drop_index("ix_sql_rules_scope_type", table_name="sql_rules")
        op.drop_table("sql_rules")
