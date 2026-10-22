"""add learning_signals table and feedback columns on thread_conversation_turns

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-10

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_signals",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "datasource_id",
            sa.String(length=255),
            sa.ForeignKey("datasources.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("thread_id", sa.String(128), nullable=True),
        sa.Column("user_question", sa.Text, nullable=False),
        sa.Column("generated_sql", sa.Text, nullable=True),
        sa.Column("sql_explanation", sa.Text, nullable=True),
        sa.Column("domain_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("pattern_hash", sa.String(64), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.add_column(
        "thread_conversation_turns",
        sa.Column("feedback_rating", sa.String(16), nullable=True),
    )
    op.add_column(
        "thread_conversation_turns",
        sa.Column("feedback_comment", sa.Text, nullable=True),
    )
    op.add_column(
        "thread_conversation_turns",
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("thread_conversation_turns", "feedback_at")
    op.drop_column("thread_conversation_turns", "feedback_comment")
    op.drop_column("thread_conversation_turns", "feedback_rating")
    op.drop_table("learning_signals")
