"""API tests for datasource memory, QA examples, and thread summary routes."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.db.models.skill_pack import SkillPack
from app.db.models.thread_context_summary import ThreadContextSummary


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    DatasourceProfile.__table__,
                    DatasourceMemoryDocument.__table__,
                    DatasourceQaExample.__table__,
                    SkillPack.__table__,
                    ThreadContextSummary.__table__,
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
        await conn.execute(
            sa.text("DELETE FROM thread_context_summaries WHERE datasource_id = 'test-admin-learning-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_memory_documents WHERE datasource_id = 'test-admin-learning-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_profiles WHERE datasource_id = 'test-admin-learning-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_qa_examples WHERE datasource_id = 'test-admin-learning-ds'")
        )
        await conn.execute(sa.text("DELETE FROM skill_packs WHERE datasource_id = 'test-admin-learning-ds'"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-admin-learning-ds'"))


@pytest.fixture(autouse=True)
def clean_learning_api_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


async def _seed_rows() -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-admin-learning-ds",
                display_name="Admin Learning DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        profile = DatasourceProfile(
            datasource_id="test-admin-learning-ds",
            summary="这是一个用于验证管理端学习流的测试数据源。",
            profile_json={
                "business_overview": "包含地区收入分析的基础事实表。",
                "data_overview": "核心事实表为 revenue_fact。",
                "metric_candidates": ["收入"],
                "entity_candidates": ["地区"],
            },
            analysis_status="ready",
        )
        memory_document = DatasourceMemoryDocument(
            datasource_id="test-admin-learning-ds",
            title="Admin Learning DS 主记忆",
            markdown_content="# Admin Learning DS 主记忆\n\n## 核心口径\n- 收入只统计已过账发票。",
            source_overview="主记忆由 Agent 基于高置信稳定信号自动维护。",
            structured_outline=[
                {"level": 1, "title": "Admin Learning DS 主记忆"},
                {"level": 2, "title": "核心口径"},
            ],
            document_metadata={
                "management_mode": "agent-managed",
                "item_count": 1,
                "recent_updates": [
                    {
                        "title": "收入口径",
                        "content": "收入只统计已过账发票。",
                        "memory_type": "business-rule",
                        "section": "全局业务口径",
                        "action": "added",
                        "source": "runtime-learning",
                        "change_summary": "补充新的稳定知识条目。",
                        "confidence": 0.91,
                        "thread_id": "thread-api",
                        "updated_at": "2026-04-09T10:00:00+00:00",
                    }
                ],
            },
        )
        draft_pack = SkillPack(
            id="draft-skill-1",
            datasource_id="test-admin-learning-ds",
            name="地区收入技能草稿",
            slug="region-revenue-draft",
            summary="针对地区收入分析的运行时草稿技能。",
            business_overview="按地区统计季度收入。",
            schema_notes=None,
            status="draft",
            origin="runtime-learning",
            activation_mode="manual",
            confidence=0.48,
            keywords=["收入", "地区"],
            metrics=[],
            entities=[],
            table_focus=[],
            business_rules=[],
            example_sql_pairs=[],
            example_questions=["按地区汇总收入。"],
            pack_metadata={"review_required": True},
            embedding_status="pending",
        )
        summary = ThreadContextSummary(
            thread_id="thread-api",
            datasource_id="test-admin-learning-ds",
            rolling_summary="## 对话摘要\n已确认收入只统计已过账发票。",
            summary_status="compressed",
            summary_metadata={"last_compacted_turn_id": 2},
            char_count=160,
            recent_turn_count=2,
            summarized_turn_count=4,
            compression_count=1,
            last_user_message="请按地区给出收入汇总。",
            last_assistant_message="可以，我会保留已过账限制。",
        )
        session.add_all(
            [
                memory_document,
                profile,
                draft_pack,
                summary,
                DatasourceQaExample(
                    id="qa-example-1",
                    datasource_id="test-admin-learning-ds",
                    skill_pack_id="draft-skill-1",
                    question="按地区汇总收入。",
                    sql="SELECT region, SUM(amount) AS revenue FROM revenue_fact GROUP BY region",
                    note="使用 revenue_fact 口径。",
                    scenario_tags=["区域分析"],
                    source="runtime-learning",
                    embedding_status="pending",
                ),
            ]
        )
        await session.commit()


def test_admin_learning_routes_cover_memory_document_qa_examples_and_thread_summaries(client) -> None:
    anyio.run(_seed_rows)

    document_res = client.get("/api/v1/admin/datasources/test-admin-learning-ds/memory-document")
    assert document_res.status_code == 200
    document_body = document_res.json()
    assert document_body["title"] == "Admin Learning DS 主记忆"
    assert "全局业务口径" in document_body["markdown_content"]
    assert document_body["management_mode"] == "agent-managed"
    assert document_body["document_metadata"]["source_of_truth"] == "memory_items"
    assert document_body["item_count"] == 1
    assert len(document_body["evidence_items"]) >= 1
    assert document_body["recent_updates"][0]["title"] == "收入口径"

    update_document_res = client.patch(
        "/api/v1/admin/datasources/test-admin-learning-ds/memory-document",
        json={
            "markdown_content": "# Admin Learning DS 主记忆\n\n## 核心口径\n- 收入只统计已过账发票。\n\n## 新增说明\n- 退票收入需单独处理。",
            "source_overview": "已由管理员直接整理。",
        },
    )
    assert update_document_res.status_code == 409
    assert "memory_document_managed_by_agent" in update_document_res.text

    qa_res = client.get("/api/v1/admin/qa-examples", params={"datasource_id": "test-admin-learning-ds"})
    assert qa_res.status_code == 200
    qa_items = qa_res.json()["items"]
    assert len(qa_items) >= 1
    assert qa_items[0]["question"] == "按地区汇总收入。"

    summaries_res = client.get(
        "/api/v1/admin/datasources/test-admin-learning-ds/thread-summaries"
    )
    assert summaries_res.status_code == 200
    assert summaries_res.json()["items"][0]["summary_status"] == "compressed"

    async def _verify_rows() -> tuple[str, list[str], str]:
        async with AsyncSessionLocal() as session:
            document = await session.get(DatasourceMemoryDocument, "test-admin-learning-ds")
            pack = await session.get(SkillPack, "draft-skill-1")
            qa_rows = await session.execute(
                select(DatasourceQaExample).where(DatasourceQaExample.datasource_id == "test-admin-learning-ds")
            )
            assert document is not None
            assert pack is not None
            return document.markdown_content, [row.question for row in qa_rows.scalars().all()], pack.status

    document_content, qa_questions, pack_status = anyio.run(_verify_rows)
    assert "收入只统计已过账发票" in document_content
    assert "退票收入需单独处理" not in document_content
    assert "按地区汇总收入。" in qa_questions
    assert pack_status == "draft"
