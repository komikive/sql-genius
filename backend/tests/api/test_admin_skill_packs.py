"""Contracts for admin skill-pack and canonical-document routes."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.core.db import async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.skill_document import SkillDocument
from app.db.models.skill_pack import SkillPack


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    SkillPack.__table__,
                    SkillDocument.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text(
                """
                ALTER TABLE skill_packs
                ADD COLUMN IF NOT EXISTS example_sql_pairs jsonb
                NOT NULL DEFAULT '[]'::jsonb
                """
            )
        )
        await conn.execute(sa.text("DELETE FROM skill_documents"))
        await conn.execute(sa.text("DELETE FROM skill_packs WHERE datasource_id LIKE 'test-%'"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id LIKE 'test-%'"))


@pytest.fixture(autouse=True)
def clean_skill_pack_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


async def _seed_skill_pack() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(
            sa.text(
                """
                INSERT INTO datasources (id, display_name, dialect, connection_url, is_default)
                VALUES ('test-skill-ds', 'Test Skill DS', 'postgresql', 'postgresql+psycopg://demo:demo@postgres:5432/sql_agent', false)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        await conn.execute(
            sa.text(
                """
                INSERT INTO skill_packs (
                  id,
                  datasource_id,
                  name,
                  slug,
                  summary,
                  business_overview,
                  schema_notes,
                  status,
                  origin,
                  activation_mode,
                  confidence,
                  keywords,
                  metrics,
                  entities,
                  table_focus,
                  business_rules,
                  example_sql_pairs,
                  example_questions,
                  pack_metadata,
                  embedding_status
                )
                VALUES (
                  :id,
                  :datasource_id,
                  :name,
                  :slug,
                  :summary,
                  :business_overview,
                  :schema_notes,
                  :status,
                  :origin,
                  :activation_mode,
                  :confidence,
                  CAST(:keywords AS jsonb),
                  CAST(:metrics AS jsonb),
                  CAST(:entities AS jsonb),
                  CAST(:table_focus AS jsonb),
                  CAST(:business_rules AS jsonb),
                  CAST(:example_sql_pairs AS jsonb),
                  CAST(:example_questions AS jsonb),
                  CAST(:pack_metadata AS jsonb),
                  :embedding_status
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": "test-skill-pack",
                "datasource_id": "test-skill-ds",
                "name": "Sales Insight",
                "slug": "sales-insight",
                "summary": "Analyze sales and customer performance.",
                "business_overview": "Initial generated overview.",
                "schema_notes": "Focus on orders and customers.",
                "status": "draft",
                "origin": "onboarding",
                "activation_mode": "auto",
                "confidence": 0.70,
                "keywords": '["sales"]',
                "metrics": "[]",
                "entities": "[]",
                "table_focus": '["orders","customers"]',
                "business_rules": "[]",
                "example_sql_pairs": "[]",
                "example_questions": "[]",
                "pack_metadata": "{}",
                "embedding_status": "pending",
            },
        )


def test_skill_pack_list_and_document_crud(
    client,
) -> None:
    anyio.run(_seed_skill_pack)

    listing = client.get("/api/v1/admin/skill-packs", params={"datasource_id": "test-skill-ds"})
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "sales-insight"

    canonical_doc = client.post(
        "/api/v1/admin/skill-packs/test-skill-pack/documents",
        json={
            "document_type": "canonical",
            "title": "Sales Insight overview",
            "content": "Initial generated overview.",
            "source": "onboarding-agent",
            "weight": 1.5,
        },
    )
    assert canonical_doc.status_code == 201, canonical_doc.text

    detail = client.get("/api/v1/admin/skill-packs/test-skill-pack")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert all(key not in detail_body for key in ("example_questions", "example_sql_pairs"))

    updated = client.patch(
        "/api/v1/admin/skill-packs/test-skill-pack",
        json={
            "summary": "Analyze sales, GMV, and customer structure.",
            "activation_mode": "manual",
            "keywords": ["sales", "gmv", "customer"],
        },
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["activation_mode"] == "manual"
    assert updated_body["summary"] == "Analyze sales, GMV, and customer structure."

    created_doc = client.post(
        "/api/v1/admin/skill-packs/test-skill-pack/documents",
        json={
            "document_type": "playbook",
            "title": "GMV 口径说明",
            "content": "GMV 不含退款订单，按已支付订单计算。",
            "weight": 1.4,
        },
    )
    assert created_doc.status_code == 201, created_doc.text
    doc_body = created_doc.json()
    assert doc_body["document_type"] == "playbook"
    assert doc_body["embedding_status"] == "pending"

    listed_docs = client.get("/api/v1/admin/skill-packs/test-skill-pack/documents")
    assert listed_docs.status_code == 200, listed_docs.text
    assert len(listed_docs.json()["items"]) >= 1

    patched_doc = client.patch(
        f"/api/v1/admin/skill-documents/{doc_body['id']}",
        json={"content": "GMV 不含退款订单，按已支付且已完成订单计算。"},
    )
    assert patched_doc.status_code == 200, patched_doc.text
    assert "已完成订单" in patched_doc.json()["content"]
    assert patched_doc.json()["embedding_status"] == "pending"

    deleted = client.delete(f"/api/v1/admin/skill-documents/{doc_body['id']}")
    assert deleted.status_code == 204, deleted.text
