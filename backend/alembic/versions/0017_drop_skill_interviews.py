"""drop retired skill interview tables

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    existing_tables = _existing_tables()

    if "skill_interview_turns" in existing_tables:
        _drop_index_if_exists("ix_skill_interview_turns_session_id", "skill_interview_turns")
        op.drop_table("skill_interview_turns")

    if "skill_interview_sessions" in existing_tables:
        _drop_index_if_exists("ix_skill_interview_sessions_status", "skill_interview_sessions")
        _drop_index_if_exists(
            "ix_skill_interview_sessions_skill_pack_id",
            "skill_interview_sessions",
        )
        op.drop_table("skill_interview_sessions")


def downgrade() -> None:
    existing_tables = _existing_tables()

    if "skill_interview_sessions" not in existing_tables:
        op.create_table(
            "skill_interview_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("skill_pack_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column(
                "phase",
                sa.String(length=32),
                nullable=False,
                server_default="discovery",
            ),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "pending_questions",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "resolved_facts",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("session_metadata", JSONB, nullable=True),
            sa.Column("last_question_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_answer_at", sa.DateTime(timezone=True), nullable=True),
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
                ["skill_pack_id"],
                ["skill_packs.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_skill_interview_sessions_skill_pack_id",
            "skill_interview_sessions",
            ["skill_pack_id"],
            unique=False,
        )
        op.create_index(
            "ix_skill_interview_sessions_status",
            "skill_interview_sessions",
            ["status"],
            unique=False,
        )

    if "skill_interview_turns" not in _existing_tables():
        op.create_table(
            "skill_interview_turns",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
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
                ["session_id"],
                ["skill_interview_sessions.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_skill_interview_turns_session_id",
            "skill_interview_turns",
            ["session_id"],
            unique=False,
        )
