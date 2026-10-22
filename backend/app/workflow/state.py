"""LangGraph workflow state for Phase 2 (routing, clarification, finalize)."""

from __future__ import annotations

from typing_extensions import TypedDict


class WorkflowState(TypedDict, total=False):
    """LangGraph 单图共享状态（checkpointer 按 thread_id 持久化，支持 interrupt/resume）。"""

    # --- 会话与数据源 ---
    thread_id: str
    datasource_id: str
    user_question: str
    runtime_mode: str

    # --- prepare_runtime 注入的上下文 ---
    memory_context: str
    recalled_memory_ids: list[str]
    recalled_memory_titles: list[str]
    thread_summary: str
    thread_summary_status: str
    recent_thread_turns: list[dict[str, str]]
    stored_turn_count: int
    recent_turn_count: int
    summarized_turn_count: int
    thread_compression_count: int
    compression_applied: bool

    # --- Agent 产出（学习审查 / turn_metadata / done 载荷）---
    activated_skill_pack_ids: list[str]
    activated_skill_pack_names: list[str]
    tool_calls_made: list[str]
    sql_execution_success: bool
    rag_chunks: list[dict]  # 预留；当前 Agent 路径未写 RAG chunk
    rag_scores: list[dict]
    generated_sql: str | None
    sql_explanation: str | None
    sql_error: str | None
    response_text: str | None
    status: str  # completed | clarified（澄清后重跑 prepare）
