"""skill packs, datasource profiles, and migration scaffolding

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-08

"""

from __future__ import annotations

import json
import re
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from app.rag.constants import DEFAULT_EMBEDDING_DIMENSION

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "skill-pack"


def _extract_table_focus(schema_scope: dict | None) -> list[str]:
    if not isinstance(schema_scope, dict):
        return []
    if isinstance(schema_scope.get("tables"), list):
        return [str(item) for item in schema_scope["tables"] if item]
    if isinstance(schema_scope.get("tables"), dict):
        return [str(key) for key in schema_scope["tables"].keys()]
    return []


def _count_tables(snapshot_payload: dict | None) -> int:
    if not isinstance(snapshot_payload, dict):
        return 0
    tables = snapshot_payload.get("tables")
    if isinstance(tables, list):
        return len(tables)
    if isinstance(tables, dict):
        return len(tables.keys())
    schemas = snapshot_payload.get("schemas")
    if isinstance(schemas, list):
        return len(schemas)
    return 0


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    if "datasource_profiles" not in existing_tables:
        op.create_table(
            "datasource_profiles",
            sa.Column("datasource_id", sa.String(length=128), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("profile_json", JSONB, nullable=True),
            sa.Column(
                "analysis_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("analysis_error", sa.Text(), nullable=True),
            sa.Column("schema_digest", sa.String(length=64), nullable=True),
            sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.PrimaryKeyConstraint("datasource_id"),
        )

    if "skill_packs" not in existing_tables:
        op.create_table(
            "skill_packs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("datasource_id", sa.String(length=128), nullable=True),
            sa.Column("legacy_domain_id", sa.String(length=128), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("business_overview", sa.Text(), nullable=True),
            sa.Column("schema_notes", sa.Text(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="draft",
            ),
            sa.Column(
                "origin",
                sa.String(length=32),
                nullable=False,
                server_default="onboarding",
            ),
            sa.Column(
                "activation_mode",
                sa.String(length=32),
                nullable=False,
                server_default="auto",
            ),
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "keywords",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "metrics",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "entities",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "table_focus",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "business_rules",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "example_questions",
                JSONB,
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("pack_metadata", JSONB, nullable=True),
            sa.Column(
                "summary_embedding",
                Vector(DEFAULT_EMBEDDING_DIMENSION),
                nullable=True,
            ),
            sa.Column(
                "embedding_status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("embedding_error", sa.Text(), nullable=True),
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
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
                ["legacy_domain_id"],
                ["business_domains.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "datasource_id",
                "slug",
                name="uq_skill_packs_datasource_slug",
            ),
        )
        op.create_index(
            "ix_skill_packs_datasource_id",
            "skill_packs",
            ["datasource_id"],
            unique=False,
        )
        op.create_index(
            "ix_skill_packs_legacy_domain_id",
            "skill_packs",
            ["legacy_domain_id"],
            unique=False,
        )
        op.create_index("ix_skill_packs_status", "skill_packs", ["status"], unique=False)

    if "skill_documents" not in existing_tables:
        op.create_table(
            "skill_documents",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
            sa.Column("skill_pack_id", sa.String(length=36), nullable=False),
            sa.Column("document_type", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=255), nullable=True),
            sa.Column(
                "weight",
                sa.Float(),
                nullable=False,
                server_default="1",
            ),
            sa.Column("document_metadata", JSONB, nullable=True),
            sa.Column(
                "embedding",
                Vector(DEFAULT_EMBEDDING_DIMENSION),
                nullable=True,
            ),
            sa.Column(
                "embedding_status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("embedding_error", sa.Text(), nullable=True),
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
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
            "ix_skill_documents_skill_pack_id",
            "skill_documents",
            ["skill_pack_id"],
            unique=False,
        )
        op.create_index(
            "ix_skill_documents_document_type",
            "skill_documents",
            ["document_type"],
            unique=False,
        )

    if "skill_interview_sessions" not in existing_tables:
        op.create_table(
            "skill_interview_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("skill_pack_id", sa.String(length=36), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="open",
            ),
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

    if "skill_interview_turns" not in existing_tables:
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

    if "skill_activation_logs" not in existing_tables:
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
            sa.ForeignKeyConstraint(
                ["skill_pack_id"],
                ["skill_packs.id"],
                ondelete="CASCADE",
            ),
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

    datasource_profiles = sa.table(
        "datasource_profiles",
        sa.column("datasource_id", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("profile_json", JSONB),
        sa.column("analysis_status", sa.String()),
        sa.column("analysis_error", sa.Text()),
        sa.column("schema_digest", sa.String()),
        sa.column("last_analyzed_at", sa.DateTime(timezone=True)),
    )
    skill_packs = sa.table(
        "skill_packs",
        sa.column("id", sa.String()),
        sa.column("datasource_id", sa.String()),
        sa.column("legacy_domain_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("business_overview", sa.Text()),
        sa.column("schema_notes", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("origin", sa.String()),
        sa.column("activation_mode", sa.String()),
        sa.column("confidence", sa.Float()),
        sa.column("keywords", JSONB),
        sa.column("metrics", JSONB),
        sa.column("entities", JSONB),
        sa.column("table_focus", JSONB),
        sa.column("business_rules", JSONB),
        sa.column("example_questions", JSONB),
        sa.column("pack_metadata", JSONB),
        sa.column("embedding_status", sa.String()),
    )

    profile_rows = bind.execute(
        sa.text(
            """
            SELECT
              d.id,
              d.display_name,
              d.dialect,
              d.created_at,
              ds.payload
            FROM datasources d
            LEFT JOIN datasource_schema_snapshots ds
              ON ds.datasource_id = d.id
            LEFT JOIN datasource_profiles dp
              ON dp.datasource_id = d.id
            WHERE dp.datasource_id IS NULL
            """
        )
    ).mappings()
    profile_payloads = [
        {
            "datasource_id": row["id"],
            "summary": (
                f"Migrated datasource profile for {row['display_name']} "
                f"({row['dialect']}); discovered {_count_tables(row['payload'])} tables."
            ),
            "profile_json": row["payload"] or {"migration_source": "legacy-admin"},
            "analysis_status": "migrated",
            "analysis_error": None,
            "schema_digest": None,
            "last_analyzed_at": row["created_at"],
        }
        for row in profile_rows
    ]
    if profile_payloads:
        bind.execute(sa.insert(datasource_profiles), profile_payloads)

    rule_rows = bind.execute(
        sa.text(
            """
            SELECT id, name, scope_type, datasource_id, domain_id, body, sort_order
            FROM sql_rules
            ORDER BY sort_order, created_at, id
            """
        )
    ).mappings()
    rules_by_domain: dict[str, list[dict[str, object]]] = {}
    rules_by_datasource: dict[str, list[dict[str, object]]] = {}
    global_rule_count = 0
    for row in rule_rows:
        payload = {
            "id": row["id"],
            "name": row["name"],
            "body": row["body"],
            "scope_type": row["scope_type"],
            "sort_order": row["sort_order"],
        }
        if row["scope_type"] == "domain" and row["domain_id"]:
            rules_by_domain.setdefault(row["domain_id"], []).append(payload)
        elif row["scope_type"] == "datasource" and row["datasource_id"]:
            rules_by_datasource.setdefault(row["datasource_id"], []).append(payload)
        elif row["scope_type"] == "global":
            global_rule_count += 1

    domain_stats_rows = bind.execute(
        sa.text(
            """
            SELECT
              col.domain_id AS domain_id,
              COUNT(DISTINCT col.id) AS collection_count,
              COUNT(kc.id) AS chunk_count
            FROM knowledge_collections col
            LEFT JOIN knowledge_chunks kc
              ON kc.collection_id = col.id
            GROUP BY col.domain_id
            """
        )
    ).mappings()
    domain_stats = {
        row["domain_id"]: {
            "collection_count": row["collection_count"],
            "chunk_count": row["chunk_count"],
        }
        for row in domain_stats_rows
    }

    existing_domain_links = {
        row["legacy_domain_id"]
        for row in bind.execute(
            sa.text(
                """
                SELECT legacy_domain_id
                FROM skill_packs
                WHERE legacy_domain_id IS NOT NULL
                """
            )
        ).mappings()
    }
    used_slugs: dict[str | None, set[str]] = {}
    existing_pack_slugs = bind.execute(
        sa.text("SELECT datasource_id, slug FROM skill_packs")
    ).mappings()
    for row in existing_pack_slugs:
        used_slugs.setdefault(row["datasource_id"], set()).add(row["slug"])

    legacy_domain_rows = bind.execute(
        sa.text(
            """
            SELECT
              bd.id,
              bd.display_name,
              bd.datasource_id,
              bd.keywords,
              bd.schema_scope,
              dsc.body AS schema_context
            FROM business_domains bd
            LEFT JOIN domain_schema_context dsc
              ON dsc.domain_id = bd.id
            ORDER BY bd.sort_order, bd.display_name, bd.id
            """
        )
    ).mappings()

    skill_pack_rows: list[dict[str, object]] = []
    datasource_with_domain_pack: set[str] = set()
    for row in legacy_domain_rows:
        if row["id"] in existing_domain_links:
            if row["datasource_id"]:
                datasource_with_domain_pack.add(row["datasource_id"])
            continue

        datasource_id = row["datasource_id"]
        slug = _slugify(row["display_name"] or row["id"])
        known = used_slugs.setdefault(datasource_id, set())
        if slug in known:
            slug = f"{slug}-{_slugify(str(row['id']))[:8]}"
        known.add(slug)

        stats = domain_stats.get(row["id"], {})
        table_focus = _extract_table_focus(row["schema_scope"])
        business_rules = rules_by_domain.get(row["id"], [])
        skill_pack_rows.append(
            {
                "id": str(uuid4()),
                "datasource_id": datasource_id,
                "legacy_domain_id": row["id"],
                "name": row["display_name"],
                "slug": slug,
                "summary": (
                    f"Migrated legacy domain '{row['display_name']}' into a datasource skill pack."
                ),
                "business_overview": row["schema_context"],
                "schema_notes": (
                    None
                    if row["schema_scope"] is None
                    else json.dumps(row["schema_scope"], ensure_ascii=True, sort_keys=True)
                ),
                "status": "ready",
                "origin": "legacy-domain",
                "activation_mode": "auto",
                "confidence": 0.58,
                "keywords": row["keywords"] or [],
                "metrics": [],
                "entities": [],
                "table_focus": table_focus,
                "business_rules": business_rules,
                "example_questions": [],
                "pack_metadata": {
                    "migration_source": "business_domain",
                    "legacy_collection_count": stats.get("collection_count", 0),
                    "legacy_chunk_count": stats.get("chunk_count", 0),
                    "datasource_rule_count": len(rules_by_datasource.get(datasource_id, []))
                    if datasource_id
                    else 0,
                    "global_rule_count": global_rule_count,
                },
                "embedding_status": "pending",
            }
        )
        if datasource_id:
            datasource_with_domain_pack.add(datasource_id)

    datasource_rows = bind.execute(
        sa.text(
            """
            SELECT
              d.id,
              d.display_name,
              d.dialect,
              ds.payload
            FROM datasources d
            LEFT JOIN datasource_schema_snapshots ds
              ON ds.datasource_id = d.id
            ORDER BY d.display_name, d.id
            """
        )
    ).mappings()
    for row in datasource_rows:
        datasource_id = row["id"]
        if datasource_id in datasource_with_domain_pack and not rules_by_datasource.get(
            datasource_id
        ):
            continue
        if datasource_id in datasource_with_domain_pack:
            continue
        slug = "general-analysis"
        known = used_slugs.setdefault(datasource_id, set())
        if slug in known:
            slug = f"{slug}-{_slugify(datasource_id)[:8]}"
        known.add(slug)
        skill_pack_rows.append(
            {
                "id": str(uuid4()),
                "datasource_id": datasource_id,
                "legacy_domain_id": None,
                "name": f"{row['display_name']} General Analysis",
                "slug": slug,
                "summary": (
                    "Fallback skill pack created during migration for datasource-level guidance."
                ),
                "business_overview": None,
                "schema_notes": None,
                "status": "draft",
                "origin": "legacy-datasource",
                "activation_mode": "manual",
                "confidence": 0.35,
                "keywords": [],
                "metrics": [],
                "entities": [],
                "table_focus": [],
                "business_rules": rules_by_datasource.get(datasource_id, []),
                "example_questions": [],
                "pack_metadata": {
                    "migration_source": "datasource-fallback",
                    "global_rule_count": global_rule_count,
                    "table_count": _count_tables(row["payload"]),
                },
                "embedding_status": "pending",
            }
        )

    if skill_pack_rows:
        bind.execute(sa.insert(skill_packs), skill_pack_rows)

    op.execute(
        sa.text(
            """
            INSERT INTO skill_documents (
              skill_pack_id,
              document_type,
              title,
              content,
              source,
              weight,
              document_metadata,
              embedding,
              embedding_status,
              embedding_error,
              embedding_updated_at,
              created_at,
              updated_at
            )
            SELECT
              sp.id,
              'knowledge-chunk',
              COALESCE(col.name, 'Legacy collection') || ' chunk #' || kc.id::text,
              kc.content,
              'legacy:knowledge_chunk:' || kc.id::text,
              1.0,
              COALESCE(kc.chunk_metadata, '{}'::jsonb) || jsonb_build_object(
                'collection_id', kc.collection_id,
                'collection_name', col.name,
                'domain_id', kc.domain_id,
                'migrated_from', 'knowledge_chunks'
              ),
              kc.embedding,
              kc.embedding_status,
              kc.embedding_error,
              kc.embedding_updated_at,
              kc.created_at,
              COALESCE(kc.embedding_updated_at, kc.created_at)
            FROM skill_packs sp
            JOIN knowledge_collections col
              ON col.domain_id = sp.legacy_domain_id
            JOIN knowledge_chunks kc
              ON kc.collection_id = col.id
            WHERE sp.legacy_domain_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM skill_documents sd
                WHERE sd.source = 'legacy:knowledge_chunk:' || kc.id::text
              )
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO skill_documents (
              skill_pack_id,
              document_type,
              title,
              content,
              source,
              weight,
              document_metadata,
              embedding_status,
              created_at,
              updated_at
            )
            SELECT
              sp.id,
              'sql-rule',
              sr.name,
              sr.body,
              'legacy:sql_rule:' || sr.id,
              1.35,
              jsonb_build_object(
                'scope_type', sr.scope_type,
                'domain_id', sr.domain_id,
                'datasource_id', sr.datasource_id,
                'sort_order', sr.sort_order,
                'migrated_from', 'sql_rules'
              ),
              'ready',
              sr.created_at,
              sr.updated_at
            FROM skill_packs sp
            JOIN sql_rules sr
              ON sr.domain_id = sp.legacy_domain_id
            WHERE sr.scope_type = 'domain'
              AND NOT EXISTS (
                SELECT 1
                FROM skill_documents sd
                WHERE sd.source = 'legacy:sql_rule:' || sr.id
              )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "skill_activation_logs" in existing_tables:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("skill_activation_logs")
        }
        if "ix_skill_activation_logs_thread_id" in existing_indexes:
            op.drop_index(
                "ix_skill_activation_logs_thread_id",
                table_name="skill_activation_logs",
            )
        if "ix_skill_activation_logs_skill_pack_id" in existing_indexes:
            op.drop_index(
                "ix_skill_activation_logs_skill_pack_id",
                table_name="skill_activation_logs",
            )
        op.drop_table("skill_activation_logs")

    if "skill_interview_turns" in existing_tables:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("skill_interview_turns")
        }
        if "ix_skill_interview_turns_session_id" in existing_indexes:
            op.drop_index(
                "ix_skill_interview_turns_session_id",
                table_name="skill_interview_turns",
            )
        op.drop_table("skill_interview_turns")

    if "skill_interview_sessions" in existing_tables:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("skill_interview_sessions")
        }
        if "ix_skill_interview_sessions_status" in existing_indexes:
            op.drop_index(
                "ix_skill_interview_sessions_status",
                table_name="skill_interview_sessions",
            )
        if "ix_skill_interview_sessions_skill_pack_id" in existing_indexes:
            op.drop_index(
                "ix_skill_interview_sessions_skill_pack_id",
                table_name="skill_interview_sessions",
            )
        op.drop_table("skill_interview_sessions")

    if "skill_documents" in existing_tables:
        existing_indexes = {index["name"] for index in inspector.get_indexes("skill_documents")}
        if "ix_skill_documents_document_type" in existing_indexes:
            op.drop_index("ix_skill_documents_document_type", table_name="skill_documents")
        if "ix_skill_documents_skill_pack_id" in existing_indexes:
            op.drop_index("ix_skill_documents_skill_pack_id", table_name="skill_documents")
        op.drop_table("skill_documents")

    if "skill_packs" in existing_tables:
        existing_indexes = {index["name"] for index in inspector.get_indexes("skill_packs")}
        if "ix_skill_packs_status" in existing_indexes:
            op.drop_index("ix_skill_packs_status", table_name="skill_packs")
        if "ix_skill_packs_legacy_domain_id" in existing_indexes:
            op.drop_index("ix_skill_packs_legacy_domain_id", table_name="skill_packs")
        if "ix_skill_packs_datasource_id" in existing_indexes:
            op.drop_index("ix_skill_packs_datasource_id", table_name="skill_packs")
        op.drop_table("skill_packs")

    if "datasource_profiles" in existing_tables:
        op.drop_table("datasource_profiles")
