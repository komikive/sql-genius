"""pgvector extension, knowledge chunks, domain schema context

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from app.rag.constants import DEFAULT_EMBEDDING_DIMENSION

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("domain_id", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            Vector(DEFAULT_EMBEDDING_DIMENSION),
            nullable=False,
        ),
        sa.Column("chunk_metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_domain_id"),
        "knowledge_chunks",
        ["domain_id"],
        unique=False,
    )

    op.create_table(
        "domain_schema_context",
        sa.Column("domain_id", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("domain_id"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO domain_schema_context (domain_id, body) VALUES
            (
              'finance',
              'Finance domain (demo): tables include invoices(id, customer_id, amount, currency, posted_at, region, quarter), '
              'customers(id, name, segment), and gl_accounts(id, code, name). Join invoices to customers on customer_id.'
            ),
            (
              'hr',
              'HR domain (demo): tables include employees(id, full_name, department, title, hire_date, salary), '
              'departments(id, name), and attendance(employee_id, day, hours).'
            ),
            (
              'general',
              'General/default domain: use conservative joins and prefer explicit time filters (e.g., posted_at, created_at).'
            )
            ON CONFLICT (domain_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("domain_schema_context")
    op.drop_index(op.f("ix_knowledge_chunks_domain_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
