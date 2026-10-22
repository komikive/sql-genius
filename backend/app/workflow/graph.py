"""Compile the LangGraph workflow for the autonomous database agent.

Architecture:
- prepare context → autonomous agent (free tool loop) → complete

The agent node wraps run_autonomous_agent which uses an LLM + Tool Loop
pattern (inspired by deepagents/hermes-agent) instead of a rigid pipeline.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.core.config import Settings
from app.core.db import AsyncSessionLocal
from app.core.observability import traced
from app.db.models.skill_pack import SkillPack
from app.services.datasource_memory import (
    build_memory_context,
    mark_memory_usage,
    recall_datasource_memory,
)
from app.services.datasource_resolve import list_resolved_datasources
from app.services.autonomous_agent import run_autonomous_agent
from app.services.thread_context import load_runtime_thread_context
from app.workflow.state import WorkflowState


def build_workflow(checkpointer: BaseCheckpointSaver, settings: Settings):
    """编译答辩主链路 LangGraph：prepare_runtime → run_agent → complete。

    - prepare：默认数据源、线程摘要压缩、主记忆召回
    - run_agent：调用 run_autonomous_agent；必要时 interrupt 澄清
    - 澄清后 status=clarified → 条件边回到 prepare，合并问题后再跑 Agent
    - custom stream（get_stream_writer）供 chat SSE 的 step 事件消费
    """

    @traced("prepare-agent-runtime", as_type="chain")
    async def prepare_runtime_node(state: WorkflowState) -> WorkflowState:
        """图节点 1：注入本轮 Agent 所需的记忆与对话上下文。"""
        writer = get_stream_writer()
        writer({"step_id": "prepare_context", "phase": "start"})
        datasource_id = (state.get("datasource_id") or "").strip() or None
        memory_context = ""
        recalled_memory_ids: list[str] = []
        recalled_memory_titles: list[str] = []
        thread_summary = ""
        thread_summary_status = "empty"
        recent_thread_turns: list[dict[str, str]] = []
        stored_turn_count = 0
        recent_turn_count = 0
        summarized_turn_count = 0
        thread_compression_count = 0
        compression_applied = False
        try:
            async with AsyncSessionLocal() as session:
                # 未显式传 datasource_id 时回退默认库（如 lab-retail-docker）
                if datasource_id is None:
                    candidates = await list_resolved_datasources(session, settings)
                    default_item = next((item for item in candidates if item.is_default), None)
                    if default_item is not None:
                        datasource_id = default_item.id
                    elif candidates:
                        datasource_id = candidates[0].id

                if datasource_id:
                    writer({"step_id": "load_thread_summary", "phase": "start"})
                    try:
                        thread_window = await load_runtime_thread_context(
                            session,
                            datasource_id=datasource_id,
                            thread_id=state.get("thread_id"),
                            current_question=state.get("user_question") or "",
                            settings=settings,
                        )
                        thread_summary = thread_window.summary
                        thread_summary_status = thread_window.summary_status
                        recent_thread_turns = thread_window.recent_turns
                        stored_turn_count = thread_window.stored_turn_count
                        recent_turn_count = thread_window.recent_turn_count
                        summarized_turn_count = thread_window.summarized_turn_count
                        thread_compression_count = thread_window.compression_count
                        compression_applied = thread_window.compression_applied
                        writer(
                            {
                                "step_id": "load_thread_summary",
                                "phase": "complete",
                                "summary_status": thread_summary_status,
                                "stored_turn_count": stored_turn_count,
                                "recent_turn_count": recent_turn_count,
                                "summarized_turn_count": summarized_turn_count,
                                "compression_count": thread_compression_count,
                                "compression_applied": compression_applied,
                            }
                        )
                    except Exception as exc:
                        await session.rollback()
                        writer(
                            {
                                "step_id": "load_thread_summary",
                                "phase": "error",
                                "error": type(exc).__name__,
                            }
                        )

                    # 向量 + 关键词混合召回主记忆条目，写入 memory_context 供 Agent 首轮 HumanMessage
                    writer({"step_id": "load_datasource_memory", "phase": "start"})
                    try:
                        recalled_entries = await recall_datasource_memory(
                            session,
                            datasource_id=datasource_id,
                            query=state.get("user_question") or "",
                            settings=settings,
                        )
                        await mark_memory_usage(
                            session,
                            datasource_id=datasource_id,
                            chunks=recalled_entries,
                        )
                        memory_context = build_memory_context(recalled_entries)
                        recalled_memory_ids = [entry.id for entry in recalled_entries]
                        recalled_memory_titles = [entry.title for entry in recalled_entries]
                        writer(
                            {
                                "step_id": "load_datasource_memory",
                                "phase": "complete",
                                "memory_count": len(recalled_memory_ids),
                                "memory_titles": recalled_memory_titles,
                            }
                        )
                    except Exception as exc:
                        await session.rollback()
                        writer(
                            {
                                "step_id": "load_datasource_memory",
                                "phase": "error",
                                "error": type(exc).__name__,
                            }
                        )

                await session.commit()
        except Exception as exc:
            writer(
                {
                    "step_id": "prepare_context",
                    "phase": "error",
                    "error": type(exc).__name__,
                }
            )

        writer(
            {
                "step_id": "prepare_context",
                "phase": "complete",
                "datasource_id": datasource_id,
                "runtime_mode": "autonomous-agent",
                "recalled_memory_titles": recalled_memory_titles,
                "thread_summary_status": thread_summary_status,
            }
        )
        return {
            "datasource_id": datasource_id,
            "runtime_mode": "autonomous-agent",
            "memory_context": memory_context,
            "recalled_memory_ids": recalled_memory_ids,
            "recalled_memory_titles": recalled_memory_titles,
            "thread_summary": thread_summary,
            "thread_summary_status": thread_summary_status,
            "recent_thread_turns": recent_thread_turns,
            "stored_turn_count": stored_turn_count,
            "recent_turn_count": recent_turn_count,
            "summarized_turn_count": summarized_turn_count,
            "thread_compression_count": thread_compression_count,
            "compression_applied": compression_applied,
        }

    @traced("run-sql-agent", as_type="agent")
    async def run_agent_node(state: WorkflowState) -> WorkflowState:
        """图节点 2：自主 Agent 工具循环；澄清走 LangGraph interrupt。"""
        writer = get_stream_writer()
        writer({"step_id": "autonomous_agent", "phase": "start"})
        datasource_id = (state.get("datasource_id") or "").strip()
        if not datasource_id:
            writer(
                {
                    "step_id": "autonomous_agent",
                    "phase": "error",
                    "error": "datasource_missing",
                }
            )
            return {
                "response_text": "当前还没有选中数据源，请先在工作台选择一个数据源后再发起提问。",
                "generated_sql": None,
                "sql_explanation": None,
                "sql_error": None,
                "activated_skill_pack_ids": [],
                "activated_skill_pack_names": [],
                "rag_chunks": [],
                "rag_scores": [],
                "status": "completed",
            }

        try:
            async with AsyncSessionLocal() as session:
                result = await run_autonomous_agent(
                    session,
                    datasource_id=datasource_id,
                    user_question=state.get("user_question") or "",
                    thread_id=state.get("thread_id"),
                    settings=settings,
                    memory_context=state.get("memory_context") or "",
                    thread_summary=state.get("thread_summary") or "",
                    recent_turns=state.get("recent_thread_turns") or [],
                    step_writer=writer,
                )
                await session.commit()
        except Exception as exc:
            writer(
                {
                    "step_id": "autonomous_agent",
                    "phase": "error",
                    "error": str(exc)[:200],
                }
            )
            return {
                "response_text": f"Agent 执行出错: {type(exc).__name__}",
                "generated_sql": None,
                "sql_explanation": None,
                "sql_error": str(exc)[:200],
                "activated_skill_pack_ids": [],
                "activated_skill_pack_names": [],
                "rag_chunks": [],
                "rag_scores": [],
                "status": "completed",
            }

        # interrupt 会暂停图执行；chat SSE 发出 event:interrupt，客户端 resume 后继续
        if result.needs_clarification:
            writer({"step_id": "clarification", "phase": "start"})
            payload = interrupt(
                {
                    "kind": "clarification",
                    "prompt": result.clarification_prompt
                    or "请补充更明确的信息。",
                }
            )
            merged = f"{state.get('user_question') or ''} {payload}".strip()
            writer({"step_id": "clarification", "phase": "complete"})
            return {
                "user_question": merged,
                "status": "clarified",
            }

        writer(
            {
                "step_id": "autonomous_agent",
                "phase": "complete",
                "steps_used": result.steps_used,
                "tool_calls": result.tool_calls_made,
                "has_sql": bool(result.generated_sql),
            }
        )
        return {
            "response_text": result.response_text,
            "generated_sql": result.generated_sql,
            "sql_explanation": result.sql_explanation,
            "sql_error": None,
            "activated_skill_pack_ids": [],
            "activated_skill_pack_names": result.activated_skill_pack_names,
            "tool_calls_made": result.tool_calls_made,
            "sql_execution_success": result.sql_execution_success,
            "rag_chunks": [],
            "rag_scores": [],
            "recalled_memory_ids": state.get("recalled_memory_ids") or [],
            "recalled_memory_titles": state.get("recalled_memory_titles") or [],
            "thread_summary_status": state.get("thread_summary_status") or "empty",
            "thread_summary": state.get("thread_summary") or "",
            "recent_turn_count": len(state.get("recent_thread_turns") or []),
            "status": "completed",
        }

    @traced("complete-agent-run", as_type="chain")
    async def complete_node(state: WorkflowState) -> WorkflowState:
        """图节点 3：收尾 trace，状态已为 completed。"""
        writer = get_stream_writer()
        writer(
            {
                "step_id": "complete",
                "phase": "complete",
                "datasource_id": state.get("datasource_id"),
                "recalled_memory_titles": state.get("recalled_memory_titles") or [],
                "thread_summary_status": state.get("thread_summary_status") or "empty",
                "has_sql": bool(state.get("generated_sql")),
            }
        )
        return {"status": "completed"}

    builder = StateGraph(WorkflowState)
    builder.add_node("prepare_runtime", prepare_runtime_node)
    builder.add_node("run_agent", run_agent_node)
    builder.add_node("complete", complete_node)
    builder.add_edge(START, "prepare_runtime")
    builder.add_edge("prepare_runtime", "run_agent")

    def _after_agent(state: WorkflowState) -> str:
        """澄清续跑：先回到 prepare 刷新上下文，再进 run_agent。"""
        return "rerun" if state.get("status") == "clarified" else "complete"

    builder.add_conditional_edges(
        "run_agent",
        _after_agent,
        {"rerun": "prepare_runtime", "complete": "complete"},
    )
    builder.add_edge("complete", END)
    return builder.compile(checkpointer=checkpointer)
