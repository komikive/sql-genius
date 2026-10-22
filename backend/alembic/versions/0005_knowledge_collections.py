"""knowledge collections and chunk lifecycle

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-08

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "knowledge_collections" not in existing_tables:
        op.create_table(
            "knowledge_collections",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("domain_id", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
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
                ["domain_id"],
                ["business_domains.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "domain_id",
                "name",
                name="uq_knowledge_collections_domain_name",
            ),
        )

    chunk_columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
    if "collection_id" not in chunk_columns:
        op.add_column(
            "knowledge_chunks",
            sa.Column("collection_id", sa.String(length=36), nullable=True),
        )
    if "embedding_status" not in chunk_columns:
        op.add_column(
            "knowledge_chunks",
            sa.Column(
                "embedding_status",
                sa.String(length=16),
                nullable=False,
                server_default="ready",
            ),
        )
    if "embedding_error" not in chunk_columns:
        op.add_column(
            "knowledge_chunks",
            sa.Column("embedding_error", sa.Text(), nullable=True),
        )
    if "embedding_updated_at" not in chunk_columns:
        op.add_column(
            "knowledge_chunks",
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.alter_column("knowledge_chunks", "embedding", nullable=True)

    existing_indexes = {index["name"] for index in inspector.get_indexes("knowledge_chunks")}
    if "ix_knowledge_chunks_collection_id" not in existing_indexes:
        op.create_index(
            "ix_knowledge_chunks_collection_id",
            "knowledge_chunks",
            ["collection_id"],
            unique=False,
        )

    constraints = {constraint["name"] for constraint in inspector.get_foreign_keys("knowledge_chunks")}
    if "knowledge_chunks_collection_id_fkey" not in constraints:
        op.create_foreign_key(
            "knowledge_chunks_collection_id_fkey",
            "knowledge_chunks",
            "knowledge_collections",
            ["collection_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.execute(
        sa.text(
            """
            INSERT INTO business_domains (id, display_name, keywords, sort_order, datasource_id, schema_scope)
            SELECT DISTINCT
              kc.domain_id,
              initcap(replace(kc.domain_id, '-', ' ')),
              '[]'::jsonb,
              500,
              NULL,
              NULL::jsonb
            FROM knowledge_chunks kc
            LEFT JOIN business_domains bd ON bd.id = kc.domain_id
            WHERE bd.id IS NULL
            ON CONFLICT (id) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO knowledge_collections (id, domain_id, name, description)
            SELECT
              md5(kc.domain_id || clock_timestamp()::text || random()::text),
              kc.domain_id,
              'Default',
              'Backfilled default collection'
            FROM (
              SELECT DISTINCT domain_id FROM knowledge_chunks
            ) kc
            LEFT JOIN knowledge_collections existing
              ON existing.domain_id = kc.domain_id
             AND existing.name = 'Default'
            WHERE existing.id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE knowledge_chunks kc
            SET
              collection_id = col.id,
              embedding_status = CASE WHEN kc.embedding IS NULL THEN 'failed' ELSE 'ready' END,
              embedding_updated_at = COALESCE(kc.created_at, now())
            FROM knowledge_collections col
            WHERE col.domain_id = kc.domain_id
              AND col.name = 'Default'
              AND kc.collection_id IS NULL
            """
        )
    )

    op.alter_column("knowledge_chunks", "collection_id", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    chunk_columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("knowledge_chunks")}
    constraints = {constraint["name"] for constraint in inspector.get_foreign_keys("knowledge_chunks")}

    if "knowledge_chunks_collection_id_fkey" in constraints:
        op.drop_constraint(
            "knowledge_chunks_collection_id_fkey",
            "knowledge_chunks",
            type_="foreignkey",
        )
    if "ix_knowledge_chunks_collection_id" in existing_indexes:
        op.drop_index("ix_knowledge_chunks_collection_id", table_name="knowledge_chunks")
    if "embedding_updated_at" in chunk_columns:
        op.drop_column("knowledge_chunks", "embedding_updated_at")
    if "embedding_error" in chunk_columns:
        op.drop_column("knowledge_chunks", "embedding_error")
    if "embedding_status" in chunk_columns:
        op.drop_column("knowledge_chunks", "embedding_status")
    if "collection_id" in chunk_columns:
        op.drop_column("knowledge_chunks", "collection_id")
    if "knowledge_collections" in existing_tables:
        op.drop_table("knowledge_collections")
