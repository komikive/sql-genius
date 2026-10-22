"""Tests for datasource QA example persistence rules."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.services import qa_examples
from app.services.qa_examples import create_runtime_qa_example


def _vec(index: int) -> list[float]:
    values = [0.0] * 1024
    values[index] = 1.0
    return values


class _FakeEmbeddings:
    def __init__(self, mapping: dict[str, list[float]]):
        self.mapping = mapping

    async def aembed_query(self, query: str) -> list[float]:
        return self.mapping[query]


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    DatasourceQaExample.__table__,
                ],
            )
        )
        await conn.execute(sa.text("DELETE FROM datasource_qa_examples WHERE datasource_id = 'test-qa-ds'"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-qa-ds'"))


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


async def _run_dedupe_flow() -> tuple[int, str, str]:
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-qa-ds",
                display_name="QA DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        await session.commit()

    settings = get_settings()
    async with AsyncSessionLocal() as session:
        await create_runtime_qa_example(
            session,
            datasource_id="test-qa-ds",
            question="按 payer 统计收入",
            sql="SELECT payer_id, SUM(amount) FROM claims GROUP BY payer_id",
            note="初始版本",
            source="runtime-learning",
            settings=settings,
        )
        await create_runtime_qa_example(
            session,
            datasource_id="test-qa-ds",
            question="按 payer 统计收入",
            sql="SELECT payer_id, SUM(paid_amount) FROM claims GROUP BY payer_id",
            note="更新版本",
            source="runtime-learning",
            settings=settings,
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            sa.select(DatasourceQaExample).where(DatasourceQaExample.datasource_id == "test-qa-ds")
        )
        items = list(rows.scalars().all())
        assert len(items) == 1
        return len(items), items[0].sql, items[0].note


def test_create_runtime_qa_example_dedupes_same_question() -> None:
    count, sql, note = anyio.run(_run_dedupe_flow)

    assert count == 1
    assert "paid_amount" in sql
    assert note == "更新版本"


async def _run_semantic_merge_flow() -> tuple[int, str]:
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-qa-ds",
                display_name="QA DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        await session.commit()

    settings = get_settings()
    mapping = {
        "按 payer 统计收入\n初始版本\n收入": _vec(0),
        "如何查看 payer 维度收入\n近义版本\n收入": _vec(0),
    }
    qa_examples.build_embedding_client = lambda _settings: _FakeEmbeddings(mapping)

    async with AsyncSessionLocal() as session:
        await create_runtime_qa_example(
            session,
            datasource_id="test-qa-ds",
            question="按 payer 统计收入",
            sql="SELECT payer_id, SUM(amount) FROM claims GROUP BY payer_id",
            note="初始版本",
            scenario_tags=["收入"],
            source="runtime-learning",
            settings=settings,
        )
        await create_runtime_qa_example(
            session,
            datasource_id="test-qa-ds",
            question="如何查看 payer 维度收入",
            sql="SELECT payer_id, SUM(paid_amount) FROM claims GROUP BY payer_id",
            note="近义版本",
            scenario_tags=["收入"],
            source="runtime-learning",
            settings=settings,
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            sa.select(DatasourceQaExample).where(DatasourceQaExample.datasource_id == "test-qa-ds")
        )
        items = list(rows.scalars().all())
        assert len(items) == 1
        return len(items), items[0].question


def test_create_runtime_qa_example_merges_semantically_similar_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qa_examples, "build_embedding_client", lambda _settings: _FakeEmbeddings({
        "按 payer 统计收入\n初始版本\n收入": _vec(0),
        "如何查看 payer 维度收入\n近义版本\n收入": _vec(0),
    }))
    count, question = anyio.run(_run_semantic_merge_flow)

    assert count == 1
    assert question in {"按 payer 统计收入", "如何查看 payer 维度收入"}
