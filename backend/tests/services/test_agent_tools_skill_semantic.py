"""Semantic retrieval tests for agent skill search."""

from __future__ import annotations

import json
from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.db.models.skill_pack import SkillPack
from app.services import agent_tools


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    SkillPack.__table__,
                    DatasourceQaExample.__table__,
                ],
            )
        )
        await conn.execute(sa.text("DELETE FROM datasource_qa_examples WHERE datasource_id = 'test-skill-semantic-ds'"))
        await conn.execute(sa.text("DELETE FROM skill_packs WHERE datasource_id = 'test-skill-semantic-ds'"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-skill-semantic-ds'"))


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


class _FakeEmbeddings:
    async def aembed_query(self, _query: str) -> list[float]:
        return [1.0] + [0.0] * 1023


def _vec(index: int) -> list[float]:
    values = [0.0] * 1024
    values[index] = 1.0
    return values


async def _run_semantic_skill_search(monkeypatch: pytest.MonkeyPatch) -> dict:
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-skill-semantic-ds",
                display_name="Skill Semantic DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        session.add_all(
            [
                SkillPack(
                    id="semantic-pack-1",
                    datasource_id="test-skill-semantic-ds",
                    name="医疗收入分析",
                    slug="medical-revenue",
                    summary="分析发票收入、支付金额和拒付金额。",
                    status="ready",
                    origin="onboarding",
                    activation_mode="auto",
                    confidence=0.90,
                    keywords=["revenue", "invoice"],
                    metrics=[],
                    entities=[],
                    table_focus=["claims", "claim_lines"],
                    business_rules=[],
                    example_sql_pairs=[{"question": "按 payer 统计收入", "sql": "SELECT payer_id, SUM(paid_amount) FROM claims GROUP BY payer_id", "note": "按 payer 汇总 paid amount"}],
                    example_questions=["按 payer 统计收入"],
                    pack_metadata={},
                    summary_embedding=_vec(0),
                    embedding_status="ready",
                ),
                SkillPack(
                    id="semantic-pack-2",
                    datasource_id="test-skill-semantic-ds",
                    name="患者留存分析",
                    slug="patient-retention",
                    summary="分析患者复诊与留存趋势。",
                    status="ready",
                    origin="onboarding",
                    activation_mode="auto",
                    confidence=0.95,
                    keywords=["retention", "patient"],
                    metrics=[],
                    entities=[],
                    table_focus=["encounters"],
                    business_rules=[],
                    example_sql_pairs=[{"question": "统计复诊率", "sql": "SELECT patient_id FROM encounters", "note": "示意"}],
                    example_questions=["统计复诊率"],
                    pack_metadata={},
                    summary_embedding=_vec(1),
                    embedding_status="ready",
                ),
                DatasourceQaExample(
                    id="semantic-qa-1",
                    datasource_id="test-skill-semantic-ds",
                    skill_pack_id="semantic-pack-1",
                    question="按 payer 统计收入",
                    sql="SELECT payer_id, SUM(paid_amount) FROM claims GROUP BY payer_id",
                    note="按 payer 汇总 paid amount",
                    scenario_tags=["收入"],
                    question_embedding=_vec(0),
                    embedding_status="ready",
                ),
                DatasourceQaExample(
                    id="semantic-qa-2",
                    datasource_id="test-skill-semantic-ds",
                    skill_pack_id="semantic-pack-2",
                    question="统计复诊率",
                    sql="SELECT patient_id FROM encounters",
                    note="示意",
                    scenario_tags=["留存"],
                    question_embedding=_vec(1),
                    embedding_status="ready",
                ),
            ]
        )
        await session.commit()

    monkeypatch.setattr(agent_tools, "build_embedding_client", lambda _settings: _FakeEmbeddings())

    async with AsyncSessionLocal() as session:
        tools = agent_tools.build_agent_tools(session, agent_tools.Settings(), "test-skill-semantic-ds")
        search_tool = next(tool for tool in tools if tool.name == "search_skills")
        raw = await search_tool.ainvoke({"query": "怎么统计发票收入和拒付金额"})
        return json.loads(raw)


def test_search_skills_prefers_semantically_closest_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = anyio.run(_run_semantic_skill_search, monkeypatch)

    assert len(payload["items"]) >= 2
    assert payload["items"][0]["name"] == "医疗收入分析"
    assert "发票收入" in payload["items"][0]["summary"]
    assert "claims" in payload["items"][0]["table_focus"]


async def _run_semantic_qa_search(monkeypatch: pytest.MonkeyPatch) -> dict:
    await _run_semantic_skill_search(monkeypatch)
    async with AsyncSessionLocal() as session:
        tools = agent_tools.build_agent_tools(session, agent_tools.Settings(), "test-skill-semantic-ds")
        search_tool = next(tool for tool in tools if tool.name == "search_qa_examples")
        raw = await search_tool.ainvoke({"query": "怎么按 payer 统计收入", "limit": 5})
        return json.loads(raw)


def test_search_qa_examples_prefers_semantically_closest_example(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = anyio.run(_run_semantic_qa_search, monkeypatch)

    assert len(payload["items"]) >= 1
    assert payload["items"][0]["question"] == "按 payer 统计收入"
    assert "SUM(paid_amount)" in payload["items"][0]["sql"]
