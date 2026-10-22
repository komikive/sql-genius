"""Focused tests for autonomous agent tools."""

from __future__ import annotations

import json
from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.thread_conversation_turn import ThreadConversationTurn
from app.services.agent_tools import build_agent_tools


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    ThreadConversationTurn.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text("DELETE FROM thread_conversation_turns WHERE datasource_id = 'test-agent-tools-ds'")
        )
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-agent-tools-ds'"))


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


async def _run_search_history_tool() -> dict:
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-agent-tools-ds",
                display_name="Agent Tools DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        session.add_all(
            [
                ThreadConversationTurn(
                    thread_id="thread-history-1",
                    datasource_id="test-agent-tools-ds",
                    role="assistant",
                    content="已按地区汇总 invoices 收入。",
                    turn_metadata={
                        "generated_sql": "SELECT region, SUM(amount) AS revenue FROM invoices GROUP BY region",
                        "sql_explanation": "按地区聚合 invoices.amount",
                    },
                ),
                ThreadConversationTurn(
                    thread_id="thread-history-2",
                    datasource_id="test-agent-tools-ds",
                    role="assistant",
                    content="这里讨论的是客户留存，不涉及发票。",
                    turn_metadata={
                        "generated_sql": "SELECT customer_id, retention_score FROM customer_retention",
                        "sql_explanation": "客户留存分析",
                    },
                ),
            ]
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        tools = build_agent_tools(session, get_settings(), "test-agent-tools-ds", thread_id="thread-history-3")
        history_tool = next(tool for tool in tools if tool.name == "search_history")
        raw = await history_tool.ainvoke({"query": "invoice", "limit": 5})
        return json.loads(raw)


def test_search_history_filters_by_query_and_returns_sql_metadata() -> None:
    payload = anyio.run(_run_search_history_tool)

    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["thread_id"] == "thread-history-1"
    assert "invoices" in (item["generated_sql"] or "")
    assert "地区" in (item["sql_explanation"] or "")
