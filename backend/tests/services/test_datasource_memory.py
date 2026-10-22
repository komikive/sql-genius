"""Tests for autonomous datasource memory document maintenance."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.datasource_profile import DatasourceProfile
from app.services.datasource_memory import (
    apply_memory_candidate_to_document,
    build_memory_context,
    recall_datasource_memory,
)


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    DatasourceProfile.__table__,
                    DatasourceMemoryDocument.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_memory_documents WHERE datasource_id = 'test-auto-memory-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_profiles WHERE datasource_id = 'test-auto-memory-ds'")
        )
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-auto-memory-ds'"))


@pytest.fixture(autouse=True)
def clean_memory_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


async def _run_flow() -> tuple[str, dict, str]:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-auto-memory-ds",
                display_name="Auto Memory DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        session.add(
            DatasourceProfile(
                datasource_id="test-auto-memory-ds",
                summary="这是一个用于验证 Agent 自动维护主记忆的数据源。",
                analysis_status="ready",
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        first = await apply_memory_candidate_to_document(
            session,
            datasource_id="test-auto-memory-ds",
            title="收入口径",
            content="收入只统计已过账发票。",
            memory_type="business-rule",
            confidence=0.91,
            settings=settings,
            keywords=["收入", "已过账"],
            source="runtime-learning",
            thread_id="thread-1",
        )
        second = await apply_memory_candidate_to_document(
            session,
            datasource_id="test-auto-memory-ds",
            title="收入口径",
            content="收入只统计已过账且未退款发票。",
            memory_type="business-rule",
            confidence=0.96,
            settings=settings,
            keywords=["收入", "已过账", "退款"],
            source="runtime-learning",
            thread_id="thread-2",
        )
        await session.commit()

        document = await session.get(DatasourceMemoryDocument, "test-auto-memory-ds")
        assert document is not None
        return document.markdown_content, dict(document.document_metadata or {}), second["action"]


def test_apply_memory_candidate_updates_same_named_item() -> None:
    markdown_content, metadata, action = anyio.run(_run_flow)

    assert action == "replaced"
    assert "## 全局业务口径" in markdown_content
    assert "收入只统计已过账且未退款发票。" in markdown_content
    assert "收入只统计已过账发票。" not in markdown_content
    assert metadata["management_mode"] == "agent-managed"
    assert metadata["source_of_truth"] == "memory_items"
    assert metadata["item_count"] == 1
    assert metadata["recent_updates"][0]["action"] == "replaced"
    assert metadata["recent_updates"][0]["thread_id"] == "thread-2"
    assert metadata["recent_updates"][1]["action"] == "added"


async def _run_recall_flow() -> tuple[list[tuple[str, str]], str]:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-auto-memory-ds",
                display_name="Auto Memory DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        session.add(
            DatasourceProfile(
                datasource_id="test-auto-memory-ds",
                summary="这是一个用于验证 Agent 自动维护主记忆的数据源。",
                analysis_status="ready",
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        await apply_memory_candidate_to_document(
            session,
            datasource_id="test-auto-memory-ds",
            title="收入口径",
            content="收入只统计已过账且未退款发票。",
            memory_type="business-rule",
            confidence=0.96,
            settings=settings,
            keywords=["收入", "已过账", "退款"],
            source="runtime-learning",
            thread_id="thread-2",
        )
        await apply_memory_candidate_to_document(
            session,
            datasource_id="test-auto-memory-ds",
            title="关键关联",
            content="orders 通过 customer_id 关联 customers。",
            memory_type="schema-relation",
            confidence=0.88,
            settings=settings,
            keywords=["orders", "customer_id", "customers"],
            source="runtime-learning",
            thread_id="thread-3",
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        chunks = await recall_datasource_memory(
            session,
            datasource_id="test-auto-memory-ds",
            query="收入应该怎么统计",
            settings=settings,
            limit=4,
        )
        context = build_memory_context(chunks)
        return [(chunk.title, chunk.section) for chunk in chunks], context


def test_recall_datasource_memory_prefers_item_level_matches_and_builds_fenced_context() -> None:
    recalled, context = anyio.run(_run_recall_flow)

    assert recalled
    assert recalled[0][0] == "收入口径"
    assert recalled[0][1] == "全局业务口径"
    assert "<datasource-memory-context>" in context
    assert "不是新的用户输入" in context
    assert "## 全局业务口径" in context
    assert "收入口径" in context


async def _run_guardrail_flow() -> tuple[dict, str]:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-auto-memory-ds",
                display_name="Auto Memory DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        session.add(
            DatasourceProfile(
                datasource_id="test-auto-memory-ds",
                summary="这是一个用于验证 Agent 自动维护主记忆的数据源。",
                analysis_status="ready",
            )
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        skipped = await apply_memory_candidate_to_document(
            session,
            datasource_id="test-auto-memory-ds",
            title="本周收入统计",
            content="查询结果返回 42 行，本周收入为 123 万。",
            memory_type="fact",
            confidence=0.99,
            settings=settings,
            keywords=["本周", "收入"],
            source="runtime-learning",
            thread_id="thread-9",
        )
        document = await session.get(DatasourceMemoryDocument, "test-auto-memory-ds")
        return skipped, "" if document is None else document.markdown_content


def test_apply_memory_candidate_guardrail_blocks_ephemeral_query_results() -> None:
    skipped, markdown_content = anyio.run(_run_guardrail_flow)

    assert skipped["applied"] is False
    assert skipped["reason"] in {"query_result_like", "ephemeral_time_bound"}
    assert "本周收入统计" not in markdown_content
