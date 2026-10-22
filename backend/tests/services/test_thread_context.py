"""Tests for datasource-scoped thread compression and rolling summaries."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.thread_context_summary import ThreadContextSummary
from app.db.models.thread_conversation_turn import ThreadConversationTurn
from app.services.thread_context import append_thread_turn, load_runtime_thread_context


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    ThreadContextSummary.__table__,
                    ThreadConversationTurn.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text("DELETE FROM thread_conversation_turns WHERE datasource_id = 'test-thread-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM thread_context_summaries WHERE datasource_id = 'test-thread-ds'")
        )
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-thread-ds'"))


@pytest.fixture(autouse=True)
def clean_thread_context_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


async def _seed_thread_rows() -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Datasource(
                id="test-thread-ds",
                display_name="Thread DS",
                dialect="postgresql",
                connection_url="postgresql+psycopg://demo:demo@postgres:5432/sql_agent",
                is_default=False,
            )
        )
        await session.flush()
        turns = [
            (
                "user",
                "请解释收入指标的业务口径，并区分已过账与未过账发票。这个口径会直接影响后续季度收入、地区收入、客户收入三类查询，所以我需要你完整记录，不要遗漏任何过滤限制。",
            ),
            (
                "assistant",
                "我先确认一下：收入是否只统计已过账发票？如果这是必须限制，我会把它视为长期业务规则，并在后续每一轮 SQL 生成时优先保留。",
            ),
            (
                "user",
                "是的，收入只统计 status=posted 的已过账发票，而且退款单和作废单都不能混进来；这部分规则是财务口径，答辩时也会被反复提问。",
            ),
            (
                "assistant",
                "明白了，我会把这个限制保留在后续生成的 SQL 中，并把退款单、作废单排除规则一起纳入长期上下文，不再每轮都重新追问。",
            ),
            (
                "user",
                "另外地区维度要来自 customers.region，而不是发票抬头；如果客户没有标准地区，就暂时归入“未知地区”，不要自行猜测城市或省份映射。",
            ),
            (
                "assistant",
                "收到，我已经记录地区字段映射，也会保留“未知地区”的兜底规则，避免后续把发票抬头误当成正式地区维度。",
            ),
            (
                "user",
                "现在请按地区给出本季度收入汇总，并在结果说明中强调口径只包含已过账发票，方便我后面直接用于论文答辩展示。",
            ),
        ]
        for role, content in turns:
            await append_thread_turn(
                session,
                datasource_id="test-thread-ds",
                thread_id="thread-compress",
                role=role,
                content=content
                + " 这是用于压缩测试的补充说明，用于验证系统会在长线程里自动生成滚动摘要，并把较早的轮次压缩成结构化上下文。"
                * 4,
            )
        await session.commit()


def test_load_runtime_thread_context_compresses_old_turns() -> None:
    anyio.run(_seed_thread_rows)

    settings = get_settings().model_copy(
        update={
            "sql_agent_thread_context_char_budget": 80,
            "sql_agent_thread_summary_char_budget": 900,
            "sql_agent_thread_context_tail_turns": 2,
            "sql_agent_thread_context_compression_min_turns": 4,
        }
    )

    async def _run():
        async with AsyncSessionLocal() as session:
            result = await load_runtime_thread_context(
                session,
                datasource_id="test-thread-ds",
                thread_id="thread-compress",
                current_question="现在请按地区给出本季度收入汇总。",
                settings=settings,
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            row = await session.get(
                ThreadContextSummary,
                ("thread-compress", "test-thread-ds"),
            )
            return result, row

    result, row = anyio.run(_run)
    assert result.compression_applied is True
    assert result.summary_status == "compressed"
    assert result.recent_turn_count == 2
    assert "已确认事实" in result.summary
    assert row is not None
    assert row.compression_count == 1
    assert row.summarized_turn_count >= 1
