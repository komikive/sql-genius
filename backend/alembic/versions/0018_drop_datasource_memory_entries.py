"""drop retired datasource memory entries

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table_name)


def _drop_foreign_key_for_column(table_name: str, column_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    for fk in inspector.get_foreign_keys(table_name):
        if fk.get("constrained_columns") == [column_name] and fk.get("name"):
            op.drop_constraint(str(fk["name"]), table_name, type_="foreignkey")


def upgrade() -> None:
    existing_tables = _existing_tables()

    if "learning_review_items" in existing_tables and "memory_entry_id" in _existing_columns(
        "learning_review_items"
    ):
        _drop_index_if_exists("ix_learning_review_items_memory_entry_id", "learning_review_items")
        _drop_foreign_key_for_column("learning_review_items", "memory_entry_id")
        op.drop_column("learning_review_items", "memory_entry_id")

    if "datasource_memory_entries" in existing_tables:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_datasource_memory_entries_fts"))
        _drop_index_if_exists("ix_datasource_memory_entries_status", "datasource_memory_entries")
        _drop_index_if_exists("ix_datasource_memory_entries_memory_type", "datasource_memory_entries")
        _drop_index_if_exists("ix_datasource_memory_entries_thread_id", "datasource_memory_entries")
        _drop_index_if_exists("ix_datasource_memory_entries_datasource_id", "datasource_memory_entries")
        op.drop_table("datasource_memory_entries")


def downgrade() -> None:
    existing_tables = _existing_tables()

    if "datasource_memory_entries" not in existing_tables:
        op.create_table(
            "datasource_memory_entries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("memory_type", sa.String(length=32), nullable=False, server_default="fact"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column(
                "source",
                sa.String(length=32),
                nullable=False,
                server_default="runtime-learning",
            ),
            sa.Column("source_excerpt", sa.Text(), nullable=True),
            sa.Column(
                "keywords",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("memory_metadata", JSONB, nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_datasource_memory_entries_datasource_id",
            "datasource_memory_entries",
            ["datasource_id"],
            unique=False,
        )
        op.create_index(
            "ix_datasource_memory_entries_thread_id",
            "datasource_memory_entries",
            ["thread_id"],
            unique=False,
        )
        op.create_index(
            "ix_datasource_memory_entries_memory_type",
            "datasource_memory_entries",
            ["memory_type"],
            unique=False,
        )
        op.create_index(
            "ix_datasource_memory_entries_status",
            "datasource_memory_entries",
            ["status"],
            unique=False,
        )
        op.execute(
            sa.text(
                """
                CREATE INDEX ix_datasource_memory_entries_fts
                ON datasource_memory_entries
                USING gin (
                  to_tsvector(
                    'simple',
                    coalesce(title, '') || ' ' || coalesce(content, '')
                  )
                )
                """
            )
        )

    if "learning_review_items" in _existing_tables() and "memory_entry_id" not in _existing_columns(
        "learning_review_items"
    ):
        op.add_column(
            "learning_review_items",
            sa.Column("memory_entry_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "learning_review_items_memory_entry_id_fkey",
            "learning_review_items",
            "datasource_memory_entries",
            ["memory_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_learning_review_items_memory_entry_id",
            "learning_review_items",
            ["memory_entry_id"],
            unique=False,
        )
