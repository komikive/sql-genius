"""retire legacy domain, knowledge, and sql-rule schema

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-09

"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _extract_rule_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, dict):
        for key in ("body", "rule", "text", "content"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _normalize_rule_entry(value: Any) -> dict[str, Any] | None:
    body = _extract_rule_text(value)
    if body is None:
        return None
    title = "运行时规则"
    scope = "datasource"
    source = "profile"
    metadata: dict[str, Any] = {}
    if isinstance(value, dict):
        raw_title = value.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            title = raw_title.strip()
        raw_scope = value.get("scope")
        if isinstance(raw_scope, str) and raw_scope.strip():
            scope = raw_scope.strip()
        raw_source = value.get("source")
        if isinstance(raw_source, str) and raw_source.strip():
            source = raw_source.strip()
        metadata = {
            key: item
            for key, item in value.items()
            if key not in {"title", "body", "rule", "text", "content", "scope", "source"}
        }
    return {
        "title": title,
        "body": body,
        "scope": scope,
        "source": source,
        **metadata,
    }


def _merge_rule_entries(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in (existing, incoming):
        if not isinstance(bucket, list):
            continue
        for item in bucket:
            normalized = _normalize_rule_entry(item)
            if normalized is None:
                continue
            body = normalized["body"]
            if body in seen:
                continue
            seen.add(body)
            merged.append(normalized)
    return merged


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    global_rule_entries: list[dict[str, Any]] = []
    datasource_rule_entries: dict[str, list[dict[str, Any]]] = {}
    domain_rule_entries: dict[str, list[dict[str, Any]]] = {}

    if "sql_rules" in existing_tables:
        rule_rows = bind.execute(
            sa.text(
                """
                SELECT id, name, scope_type, datasource_id, domain_id, body, sort_order
                FROM sql_rules
                WHERE enabled IS TRUE
                ORDER BY sort_order, created_at, id
                """
            )
        ).mappings()
        for row in rule_rows:
            entry = {
                "title": row["name"] or "迁移规则",
                "body": row["body"],
                "scope": row["scope_type"],
                "source": "migrated-sql-rule",
                "migrated_rule_id": row["id"],
                "sort_order": row["sort_order"],
            }
            if row["scope_type"] == "global":
                global_rule_entries.append(entry)
            elif row["scope_type"] == "datasource" and row["datasource_id"]:
                datasource_rule_entries.setdefault(row["datasource_id"], []).append(entry)
            elif row["scope_type"] == "domain" and row["domain_id"]:
                domain_rule_entries.setdefault(row["domain_id"], []).append(entry)

    if {"datasources", "datasource_profiles"}.issubset(existing_tables):
        datasource_ids = [
            row["id"]
            for row in bind.execute(sa.text("SELECT id FROM datasources")).mappings()
        ]
        existing_profiles = {
            row["datasource_id"]: row["profile_json"]
            for row in bind.execute(
                sa.text("SELECT datasource_id, profile_json FROM datasource_profiles")
            ).mappings()
        }
        for datasource_id in datasource_ids:
            incoming_rules = [
                *global_rule_entries,
                *datasource_rule_entries.get(datasource_id, []),
            ]
            if not incoming_rules:
                continue
            if datasource_id not in existing_profiles:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO datasource_profiles (
                          datasource_id,
                          summary,
                          profile_json,
                          analysis_status
                        )
                        VALUES (:datasource_id, '', '{}'::jsonb, 'pending')
                        ON CONFLICT (datasource_id) DO NOTHING
                        """
                    ),
                    {"datasource_id": datasource_id},
                )
                existing_profiles[datasource_id] = {}
            payload = (
                dict(existing_profiles[datasource_id])
                if isinstance(existing_profiles[datasource_id], dict)
                else {}
            )
            payload["runtime_rules"] = _merge_rule_entries(
                payload.get("runtime_rules"),
                incoming_rules,
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE datasource_profiles
                    SET profile_json = CAST(:profile_json AS jsonb)
                    WHERE datasource_id = :datasource_id
                    """
                ),
                {
                    "datasource_id": datasource_id,
                    "profile_json": json.dumps(payload, ensure_ascii=True),
                },
            )

    if {"skill_packs", "skill_documents"}.issubset(existing_tables):
        if "sql_rules" in existing_tables:
            pack_rows = bind.execute(
                sa.text(
                    """
                    SELECT id, legacy_domain_id, business_rules
                    FROM skill_packs
                    WHERE legacy_domain_id IS NOT NULL
                    """
                )
            ).mappings()
            for row in pack_rows:
                domain_id = row["legacy_domain_id"]
                merged_rules = _merge_rule_entries(
                    row["business_rules"],
                    domain_rule_entries.get(domain_id, []),
                )
                bind.execute(
                    sa.text(
                        """
                        UPDATE skill_packs
                        SET business_rules = CAST(:business_rules AS jsonb)
                        WHERE id = :skill_pack_id
                        """
                    ),
                    {
                        "skill_pack_id": row["id"],
                        "business_rules": json.dumps(merged_rules, ensure_ascii=True),
                    },
                )

        if "domain_schema_context" in existing_tables:
            op.execute(
                sa.text(
                    "DELETE FROM skill_documents WHERE source LIKE 'legacy:domain_schema_context:%'"
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
                      'schema-context',
                      sp.name || ' schema context',
                      dsc.body,
                      'legacy:domain_schema_context:' || dsc.domain_id,
                      1.1,
                      jsonb_build_object(
                        'domain_id', dsc.domain_id,
                        'migrated_from', 'domain_schema_context'
                      ),
                      'pending',
                      now(),
                      now()
                    FROM skill_packs sp
                    JOIN domain_schema_context dsc
                      ON dsc.domain_id = sp.legacy_domain_id
                    WHERE sp.legacy_domain_id IS NOT NULL
                      AND length(trim(COALESCE(dsc.body, ''))) > 0
                    """
                )
            )

        if {"knowledge_collections", "knowledge_chunks"}.issubset(existing_tables):
            op.execute(
                sa.text("DELETE FROM skill_documents WHERE source LIKE 'legacy:knowledge_chunk:%'")
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
                    """
                )
            )

        if "sql_rules" in existing_tables:
            op.execute(
                sa.text("DELETE FROM skill_documents WHERE source LIKE 'legacy:sql_rule:%'")
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
                    """
                )
            )

    if "skill_packs" in existing_tables:
        op.execute(sa.text("ALTER TABLE skill_packs DROP COLUMN IF EXISTS legacy_domain_id"))
    if "admin_sessions" in existing_tables:
        op.execute(sa.text("ALTER TABLE admin_sessions DROP COLUMN IF EXISTS latest_domain_id"))

    if "knowledge_chunks" in existing_tables:
        op.drop_table("knowledge_chunks")
    if "knowledge_collections" in existing_tables:
        op.drop_table("knowledge_collections")
    if "domain_schema_context" in existing_tables:
        op.drop_table("domain_schema_context")
    if "sql_rules" in existing_tables:
        op.drop_table("sql_rules")
    if "business_domains" in existing_tables:
        op.drop_table("business_domains")


def downgrade() -> None:
    # The legacy compatibility schema is intentionally retired.
    pass
