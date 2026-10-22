"""SSE chat stream: LangGraph interrupt + resume (Phase 2)."""

from __future__ import annotations

import anyio
import sqlalchemy as sa

from app.api.routers import chat as chat_router
from app.core.db import async_engine
from app.db.base import Base
from app.db.models.admin_session import AdminSession
from app.db.models.datasource import Datasource
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.skill_pack import SkillPack
from app.db.models.thread_context_summary import ThreadContextSummary
from app.db.models.thread_conversation_turn import ThreadConversationTurn
from app.services.autonomous_agent import AgentResult
from app.services.learning_review import LearningReviewResult
from app.workflow import graph as workflow_graph


def test_suggestion_parser_accepts_multiline_quoted_items_without_commas() -> None:
    raw = '''["哪个供应商提供的原材料批次平均缺陷成本最高？"
"过去一个月中，按严重性统计各停机事件导致的总分钟数损失是多少？"
"哪三条生产线的自动化水平最高且二氧化碳排放量最低？"
"哪些工作订单的废品率超过了10%且对应的质量检验状态为不合格？"]'''

    items = chat_router._coerce_suggestion_items(raw, 4)

    assert len(items) == 4
    assert items[0] == "哪个供应商提供的原材料批次平均缺陷成本最高？"
    assert items[1].startswith("过去一个月中")


def test_suggestion_quality_filter_rejects_fabricated_year_and_quarter() -> None:
    items = [
        "2023年第四季度各工厂的能耗变化趋势如何？",
        "哪些机器在上季度停机最严重？",
    ]

    assert chat_router._suggestions_need_grounded_fallback(items) is True


def test_grounded_fallback_generates_datasource_specific_manufacturing_questions() -> None:
    schema_payload = {
        "tables": [
            {"name": "plants", "columns": []},
            {"name": "production_lines", "columns": []},
            {"name": "machines", "columns": []},
            {"name": "work_orders", "columns": []},
            {"name": "downtime_events", "columns": []},
        ]
    }

    items = chat_router._grounded_fallback_suggestions(
        "lab-manufacturing-docker",
        "覆盖工厂、产线、工单、设备传感器、停机、维修、质检和能源使用的工业场景。",
        schema_payload,
        4,
    )

    assert len(items) == 4
    assert items[0] == "哪些产线的计划产量与实际产量差距最大？"
    assert any("停机" in item for item in items)


def test_chat_stream_rejects_an_active_run_for_the_same_thread(client, app) -> None:
    original_guard = app.state.thread_run_guard

    class BusyGuard:
        async def try_acquire(self, thread_id: str) -> bool:
            return False

    app.state.thread_run_guard = BusyGuard()
    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "thread_id": "busy-thread",
                "datasource_id": "11111111-1111-1111-1111-111111111111",
                "message": "run",
            },
        )
    finally:
        app.state.thread_run_guard = original_guard

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "thread_busy"


def test_chat_stream_releases_thread_guard_after_stream(client, monkeypatch) -> None:
    async def fake_stream(*args, **kwargs):
        yield b"event: done\ndata: {}\n\n"

    monkeypatch.setattr(chat_router, "_stream_chat_events", fake_stream)
    body = {
        "thread_id": "released-thread",
        "datasource_id": "11111111-1111-1111-1111-111111111111",
        "message": "run",
    }

    assert client.post("/api/v1/chat/stream", json=body).status_code == 200
    assert client.post("/api/v1/chat/stream", json=body).status_code == 200


async def _prepare_chat_runtime_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    AdminSession.__table__,
                    DatasourceMemoryDocument.__table__,
                    SkillPack.__table__,
                    ThreadContextSummary.__table__,
                    ThreadConversationTurn.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text("DELETE FROM thread_conversation_turns WHERE datasource_id = 'test-chat-skill-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM thread_conversation_turns WHERE thread_id LIKE 'test-chat-%'")
        )
        await conn.execute(
            sa.text("DELETE FROM thread_context_summaries WHERE datasource_id = 'test-chat-skill-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM thread_context_summaries WHERE thread_id LIKE 'test-chat-%'")
        )
        await conn.execute(sa.text("DELETE FROM admin_sessions WHERE thread_id LIKE 'test-chat-%'"))
        await conn.execute(
            sa.text("DELETE FROM datasource_memory_documents WHERE datasource_id = 'test-chat-skill-ds'")
        )
        await conn.execute(
            sa.text("DELETE FROM datasource_memory_documents WHERE datasource_id = 'test-chat-empty-ds'")
        )
        await conn.execute(sa.text("DELETE FROM skill_packs WHERE datasource_id = 'test-chat-skill-ds'"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-chat-skill-ds'"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id = 'test-chat-empty-ds'"))


async def _seed_chat_runtime_datasource() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(
            sa.text(
                """
                INSERT INTO datasources (id, display_name, dialect, connection_url, is_default)
                VALUES ('test-chat-skill-ds', 'Chat Skill DS', 'postgresql', 'postgresql+psycopg://demo:demo@postgres:5432/sql_agent', false)
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
                  example_questions,
                  pack_metadata,
                  embedding_status
                )
                VALUES (
                  'test-chat-skill-pack',
                  'test-chat-skill-ds',
                  'Revenue Skill',
                  'revenue-skill',
                  'Answer revenue analysis questions.',
                  'Focused on revenue metrics.',
                  'Uses invoices and customers.',
                  'ready',
                  'onboarding',
                  'auto',
                  0.85,
                  '["revenue"]'::jsonb,
                  '[]'::jsonb,
                  '[]'::jsonb,
                  '["invoices","customers"]'::jsonb,
                  '[]'::jsonb,
                  '[]'::jsonb,
                  '{}'::jsonb,
                  'pending'
                )
                ON CONFLICT (id) DO NOTHING
                """
            )
        )


async def _seed_empty_runtime_datasource() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(
            sa.text(
                """
                INSERT INTO datasources (id, display_name, dialect, connection_url, is_default)
                VALUES ('test-chat-empty-ds', 'Chat Empty DS', 'postgresql', 'postgresql+psycopg://demo:demo@postgres:5432/sql_agent', false)
                ON CONFLICT (id) DO NOTHING
                """
            )
        )


def test_chat_stream_interrupt_and_resume(client, monkeypatch):
    anyio.run(_prepare_chat_runtime_tables)
    anyio.run(_seed_chat_runtime_datasource)

    async def _fake_agent(*_args, **kwargs):
        question = kwargs.get("user_question") or ""
        step_writer = kwargs.get("step_writer")
        if question == "hi":
            if step_writer:
                step_writer({"step_id": "reasoning_note", "phase": "note", "text": "需要更多业务上下文。"})
            return AgentResult(
                needs_clarification=True,
                clarification_prompt="请补充更明确的业务对象、时间范围或指标口径。",
            )
        if step_writer:
            step_writer({
                "step_id": "tool_call",
                "phase": "complete",
                "tool": "introspect_schema",
                "summary": "读取到 invoices 与 customers 表",
            })
            step_writer({
                "step_id": "assistant_message",
                "phase": "complete",
                "content": "已完成澄清后的查询分析。",
            })
        return AgentResult(
            response_text="已完成澄清后的查询分析。",
            generated_sql="SELECT region, SUM(amount) AS revenue FROM invoices GROUP BY region",
            sql_explanation="按地区汇总收入。",
            tool_calls_made=["introspect_schema", "execute_query"],
            steps_used=2,
        )

    original = workflow_graph.run_autonomous_agent
    workflow_graph.run_autonomous_agent = _fake_agent

    async def _fake_learning_review(*_args, **_kwargs):
        return LearningReviewResult(
            memory_count=1,
            memory_updates=[
                {
                    "title": "Q3 收入口径",
                    "content": "Q3 收入分析默认按 invoices.amount 汇总。",
                    "section": "全局业务口径",
                    "action": "added",
                    "confidence": 0.93,
                    "change_summary": "补充新的稳定知识条目。",
                    "updated_at": "2026-04-09T10:00:00+00:00",
                }
            ],
        )

    monkeypatch.setattr(chat_router, "run_post_turn_learning_review", _fake_learning_review)
    tid = "test-chat-interrupt-resume"
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "thread_id": tid,
                "datasource_id": "test-chat-skill-ds",
                "message": "hi",
                "resume": False,
            },
        ) as response:
            first = response.read().decode()

        assert "event: interrupt" in first
        assert "prepare_context" in first
        assert "autonomous_agent" in first
        assert "clarification" in first

        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "thread_id": tid,
                "datasource_id": "test-chat-skill-ds",
                "message": "Show Q3 revenue by region.",
                "resume": True,
            },
        ) as response:
            second = response.read().decode()
    finally:
        workflow_graph.run_autonomous_agent = original
        anyio.run(_prepare_chat_runtime_tables)

    assert "event: done" in second
    assert "autonomous_agent" in second
    assert "memory_autoupdate" in second
    assert "Q3 收入口径" in second
    assert "assistant_turn_id" in second
    assert "已完成澄清后的查询分析" in second


def test_chat_stream_without_skill_packs_returns_guidance(client, monkeypatch):
    anyio.run(_prepare_chat_runtime_tables)
    anyio.run(_seed_empty_runtime_datasource)

    async def _fake_agent(*_args, **kwargs):
        step_writer = kwargs.get("step_writer")
        if step_writer:
            step_writer({"step_id": "reasoning_note", "phase": "note", "text": "当前数据源没有技能包，改为直接基于 schema 分析。"})
            step_writer({"step_id": "assistant_message", "phase": "complete", "content": "当前数据源暂无技能包，但仍可基于 schema 继续分析。"})
        return AgentResult(
            response_text="当前数据源暂无技能包，但仍可基于 schema 继续分析。",
            steps_used=1,
        )

    monkeypatch.setattr(workflow_graph, "run_autonomous_agent", _fake_agent)
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "thread_id": "test-chat-empty-guidance",
                "datasource_id": "test-chat-empty-ds",
                "message": "Show revenue by region.",
                "resume": False,
            },
        ) as response:
            body = response.read().decode()
    finally:
        anyio.run(_prepare_chat_runtime_tables)

    assert "event: done" in body
    assert "autonomous_agent" in body
    assert "当前数据源暂无技能包，但仍可基于 schema 继续分析。" in body


def test_chat_stream_emits_error_done_when_workflow_raises(client):
    anyio.run(_prepare_chat_runtime_tables)
    original = client.app.state.workflow

    class BrokenWorkflow:
        async def astream(self, *args, **kwargs):
            if False:
                yield ("custom", {})
            raise RuntimeError("stream exploded during test")

    client.app.state.workflow = BrokenWorkflow()
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "thread_id": "test-chat-stream-error",
                "message": "trigger failure",
                "resume": False,
            },
        ) as response:
            body = response.read().decode()
    finally:
        client.app.state.workflow = original
        anyio.run(_prepare_chat_runtime_tables)

    assert "event: done" in body
    assert '"ok": false' in body
    assert "stream exploded during test" in body


def test_chat_stream_uses_autonomous_agent_when_datasource_has_skill_packs(client, monkeypatch):
    anyio.run(_prepare_chat_runtime_tables)
    anyio.run(_seed_chat_runtime_datasource)

    async def _fake_agent(*_args, **kwargs):
        step_writer = kwargs.get("step_writer")
        if step_writer:
            step_writer({"step_id": "reasoning_note", "phase": "note", "text": "先检查 schema，再执行聚合查询。"})
            step_writer({
                "step_id": "tool_call",
                "phase": "complete",
                "tool": "search_skills",
                "summary": "找到 1 个候选技能包",
                "result_preview": "Revenue Skill",
            })
            step_writer({
                "step_id": "assistant_message",
                "phase": "complete",
                "content": "已基于可用上下文完成收入分析。",
            })
        return AgentResult(
            response_text="已基于可用上下文完成收入分析。",
            generated_sql="SELECT region, SUM(amount) AS revenue FROM invoices GROUP BY region",
            sql_explanation="Used the revenue skill pack for invoice aggregation.",
            tool_calls_made=["search_skills", "execute_query"],
            steps_used=2,
        )

    monkeypatch.setattr(workflow_graph, "run_autonomous_agent", _fake_agent)
    try:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={
                "thread_id": "test-chat-autonomous-agent",
                "datasource_id": "test-chat-skill-ds",
                "message": "Show revenue by region.",
                "resume": False,
            },
        ) as response:
            body = response.read().decode()
    finally:
        anyio.run(_prepare_chat_runtime_tables)

    assert "event: done" in body
    assert "prepare_context" in body
    assert "autonomous_agent" in body
    assert "Revenue Skill" in body
    assert "assistant_turn_id" in body
