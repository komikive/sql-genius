"""datasource memory, thread summaries, and learning review queue

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "datasource_memory_entries" not in existing_tables:
        op.create_table(
            "datasource_memory_entries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "memory_type",
                sa.String(length=32),
                nullable=False,
                server_default="fact",
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
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
            sa.Column(
                "usage_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
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
            sa.ForeignKeyConstraint(
                ["datasource_id"],
                ["datasources.id"],
                ondelete="CASCADE",
            ),
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

    if "thread_context_summaries" not in existing_tables:
        op.create_table(
            "thread_context_summaries",
            sa.Column("thread_id", sa.String(length=128), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("rolling_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "summary_status",
                sa.String(length=32),
                nullable=False,
                server_default="fresh",
            ),
            sa.Column("summary_metadata", JSONB, nullable=True),
            sa.Column(
                "char_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "recent_turn_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "summarized_turn_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "compression_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("last_user_message", sa.Text(), nullable=True),
            sa.Column("last_assistant_message", sa.Text(), nullable=True),
            sa.Column("last_compacted_at", sa.DateTime(timezone=True), nullable=True),
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
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("thread_id", "datasource_id"),
        )
        op.create_index(
            "ix_thread_context_summaries_datasource_id",
            "thread_context_summaries",
            ["datasource_id"],
            unique=False,
        )
        op.create_index(
            "ix_thread_context_summaries_summary_status",
            "thread_context_summaries",
            ["summary_status"],
            unique=False,
        )

    if "thread_conversation_turns" not in existing_tables:
        op.create_table(
            "thread_conversation_turns",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("turn_metadata", JSONB, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["datasource_id"],
                ["datasources.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_thread_conversation_turns_thread_id",
            "thread_conversation_turns",
            ["thread_id"],
            unique=False,
        )
        op.create_index(
            "ix_thread_conversation_turns_datasource_id",
            "thread_conversation_turns",
            ["datasource_id"],
            unique=False,
        )
        op.create_index(
            "ix_thread_conversation_turns_role",
            "thread_conversation_turns",
            ["role"],
            unique=False,
        )
        op.create_index(
            "ix_thread_conversation_turns_thread_window",
            "thread_conversation_turns",
            ["datasource_id", "thread_id", "id"],
            unique=False,
        )

    if "learning_review_items" not in existing_tables:
        op.create_table(
            "learning_review_items",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("review_kind", sa.String(length=32), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "source",
                sa.String(length=32),
                nullable=False,
                server_default="runtime-review",
            ),
            sa.Column("payload", JSONB, nullable=True),
            sa.Column("memory_entry_id", sa.String(length=36), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["datasource_id"],
                ["datasources.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["memory_entry_id"],
                ["datasource_memory_entries.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["skill_pack_id"],
                ["skill_packs.id"],
                ondelete="SET NULL",
            ),
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
            "ix_learning_review_items_memory_entry_id",
            "learning_review_items",
            ["memory_entry_id"],
            unique=False,
        )
        op.create_index(
            "ix_learning_review_items_skill_pack_id",
            "learning_review_items",
            ["skill_pack_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "learning_review_items" in existing_tables:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_learning_review_items_skill_pack_id"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_learning_review_items_memory_entry_id"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_learning_review_items_status"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_learning_review_items_review_kind"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_learning_review_items_thread_id"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_learning_review_items_datasource_id"))
        op.drop_table("learning_review_items")

    if "thread_conversation_turns" in existing_tables:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_thread_conversation_turns_thread_window"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_thread_conversation_turns_role"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_thread_conversation_turns_datasource_id"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_thread_conversation_turns_thread_id"))
        op.drop_table("thread_conversation_turns")

    if "thread_context_summaries" in existing_tables:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_thread_context_summaries_summary_status"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_thread_context_summaries_datasource_id"))
        op.drop_table("thread_context_summaries")

    if "datasource_memory_entries" in existing_tables:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_datasource_memory_entries_fts"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_datasource_memory_entries_status"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_datasource_memory_entries_memory_type"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_datasource_memory_entries_thread_id"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_datasource_memory_entries_datasource_id"))
        op.drop_table("datasource_memory_entries")
