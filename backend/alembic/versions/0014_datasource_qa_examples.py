"""add datasource qa example retrieval layer

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-15
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "datasource_qa_examples" not in existing_tables:
        op.create_table(
            "datasource_qa_examples",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("datasource_id", sa.String(length=128), sa.ForeignKey("datasources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("skill_pack_id", sa.String(length=36), sa.ForeignKey("skill_packs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("sql", sa.Text(), nullable=False, server_default=""),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("scenario_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="skill-pack"),
            sa.Column("source_metadata", sa.JSON(), nullable=True),
            sa.Column("question_embedding", Vector(1024), nullable=True),
            sa.Column("embedding_status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("embedding_error", sa.Text(), nullable=True),
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_datasource_qa_examples_datasource_id", "datasource_qa_examples", ["datasource_id"])
        op.create_index("ix_datasource_qa_examples_skill_pack_id", "datasource_qa_examples", ["skill_pack_id"])

    if {"datasource_qa_examples", "skill_packs"}.issubset(existing_tables | {"datasource_qa_examples"}):
        skill_rows = bind.execute(
            sa.text(
                """
                SELECT id, datasource_id, name, slug, example_sql_pairs
                FROM skill_packs
                WHERE datasource_id IS NOT NULL
                ORDER BY id
                """
            )
        ).mappings()
        now = datetime.now(timezone.utc)
        for row in skill_rows:
            pairs = row.get("example_sql_pairs") or []
            if not isinstance(pairs, list):
                continue
            for index, item in enumerate(pairs, start=1):
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question") or "").strip()
                if not question:
                    continue
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO datasource_qa_examples (
                            id, datasource_id, skill_pack_id, question, sql, note, scenario_tags,
                            source, source_metadata, question_embedding, embedding_status,
                            embedding_error, embedding_updated_at, created_at, updated_at
                        ) VALUES (
                            :id, :datasource_id, :skill_pack_id, :question, :sql, :note, CAST(:scenario_tags AS jsonb),
                            'skill-pack', CAST(:source_metadata AS jsonb), NULL, 'pending',
                            NULL, NULL, :created_at, :updated_at
                        )
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {
                        "id": str(uuid5(NAMESPACE_URL, f"skill-pack-qa:{row['id']}:{index}")),
                        "datasource_id": row["datasource_id"],
                        "skill_pack_id": row["id"],
                        "question": question,
                        "sql": str(item.get("sql") or ""),
                        "note": str(item.get("note") or ""),
                        "scenario_tags": json.dumps(item.get("scenario_tags") or [], ensure_ascii=True),
                        "source_metadata": json.dumps({"skill_pack_name": row["name"], "skill_pack_slug": row["slug"]}, ensure_ascii=True),
                        "created_at": now,
                        "updated_at": now,
                    },
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "datasource_qa_examples" in existing_tables:
        op.drop_index("ix_datasource_qa_examples_skill_pack_id", table_name="datasource_qa_examples")
        op.drop_index("ix_datasource_qa_examples_datasource_id", table_name="datasource_qa_examples")
        op.drop_table("datasource_qa_examples")
