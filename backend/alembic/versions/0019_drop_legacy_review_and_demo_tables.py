"""drop legacy review, activation, and demo tables

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = _existing_tables()

    if "datasources" in existing_tables:
        bind.execute(
            sa.text("DELETE FROM datasources WHERE id = :datasource_id"),
            {"datasource_id": "admin-demo-docker"},
        )

    if "learning_review_items" in existing_tables:
        _drop_index_if_exists("ix_learning_review_items_skill_pack_id", "learning_review_items")
        _drop_index_if_exists("ix_learning_review_items_status", "learning_review_items")
        _drop_index_if_exists("ix_learning_review_items_review_kind", "learning_review_items")
        _drop_index_if_exists("ix_learning_review_items_thread_id", "learning_review_items")
        _drop_index_if_exists("ix_learning_review_items_datasource_id", "learning_review_items")
        op.drop_table("learning_review_items")

    if "skill_activation_logs" in existing_tables:
        _drop_index_if_exists("ix_skill_activation_logs_thread_id", "skill_activation_logs")
        _drop_index_if_exists("ix_skill_activation_logs_skill_pack_id", "skill_activation_logs")
        op.drop_table("skill_activation_logs")

    if "foundation_meta" in existing_tables:
        op.drop_table("foundation_meta")

    if "invoices" in existing_tables:
        op.drop_table("invoices")
    if "customers" in existing_tables:
        op.drop_table("customers")


def downgrade() -> None:
    existing_tables = _existing_tables()

    if "foundation_meta" not in existing_tables:
        op.create_table(
            "foundation_meta",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("note", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "skill_activation_logs" not in _existing_tables():
        op.create_table(
            "skill_activation_logs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("skill_pack_id", sa.String(length=36), nullable=False),
            sa.Column("thread_id", sa.String(length=255), nullable=True),
            sa.Column("question_excerpt", sa.Text(), nullable=True),
            sa.Column("activation_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("selection_score", sa.Float(), nullable=True),
            sa.Column(
                "selected_by",
                sa.String(length=32),
                nullable=False,
                server_default="runtime-agent",
            ),
            sa.Column("log_metadata", JSONB, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["skill_pack_id"], ["skill_packs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_skill_activation_logs_skill_pack_id",
            "skill_activation_logs",
            ["skill_pack_id"],
            unique=False,
        )
        op.create_index(
            "ix_skill_activation_logs_thread_id",
            "skill_activation_logs",
            ["thread_id"],
            unique=False,
        )

    if "learning_review_items" not in _existing_tables():
        op.create_table(
            "learning_review_items",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("review_kind", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="runtime-review"),
            sa.Column("payload", JSONB, nullable=True),
            sa.Column("skill_pack_id", sa.String(length=36), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(["datasource_id"], ["datasources.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["skill_pack_id"], ["skill_packs.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_learning_review_items_datasource_id",
            "learning_review_items",
            ["datasource_id"],
            unique=False,
        )
        op.create_index(
            "ix_learning_review_items_thread_id",
            "learning_review_items",
            ["thread_id"],
            unique=False,
        )
        op.create_index(
            "ix_learning_review_items_review_kind",
            "learning_review_items",
            ["review_kind"],
            unique=False,
        )
        op.create_index(
            "ix_learning_review_items_status",
            "learning_review_items",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_learning_review_items_skill_pack_id",
            "learning_review_items",
            ["skill_pack_id"],
            unique=False,
        )
