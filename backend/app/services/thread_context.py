"""Datasource-aware thread turns, rolling summaries, and context compression."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.llm_structured import content_to_text, parse_model_output
from app.db.models.thread_context_summary import ThreadContextSummary
from app.db.models.thread_conversation_turn import ThreadConversationTurn

_CONSTRAINT_RE = re.compile(r"(只|仅|必须|不能|禁止|排除|口径|过滤|限定)")


def _truncate(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(limit - 3, 1)] + "..."


def _excerpt(text: str, limit: int = 220) -> str:
    return _truncate(" ".join((text or "").split()), limit)


def _render_structured_summary(
    *,
    summary: str,
    resolved_facts: list[str],
    constraints: list[str],
    open_questions: list[str],
) -> str:
    sections = [f"## 对话摘要\n{summary.strip() or '暂无摘要。'}"]
    if resolved_facts:
        sections.append(
            "## 已确认事实\n" + "\n".join(f"- {item}" for item in resolved_facts[:6])
        )
    if constraints:
        sections.append(
            "## 关键约束\n" + "\n".join(f"- {item}" for item in constraints[:5])
        )
    if open_questions:
        sections.append(
            "## 待确认问题\n" + "\n".join(f"- {item}" for item in open_questions[:4])
        )
    return "\n\n".join(section.strip() for section in sections if section.strip())


class ThreadSummaryOutput(BaseModel):
    summary: str = Field(..., min_length=1)
    resolved_facts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class ThreadContextWindow:
    summary: str
    summary_status: str
    recent_turns: list[dict[str, str]]
    stored_turn_count: int
    recent_turn_count: int
    summarized_turn_count: int
    compression_count: int
    compression_applied: bool


def _heuristic_summary_output(
    *,
    existing_summary: str,
    turns: list[ThreadConversationTurn],
) -> ThreadSummaryOutput:
    user_lines = [
        _excerpt(turn.content)
        for turn in turns
        if turn.role == "user" and turn.content.strip()
    ]
    assistant_lines = [
        _excerpt(turn.content)
        for turn in turns
        if turn.role == "assistant" and turn.content.strip()
    ]
    resolved_facts = list(dict.fromkeys(line for line in user_lines if len(line) >= 8))[:6]
    constraints = list(
        dict.fromkeys(
            line
            for line in [*user_lines, *assistant_lines]
            if _CONSTRAINT_RE.search(line)
        )
    )[:5]
    open_questions = list(
        dict.fromkeys(
            line
            for line in assistant_lines
            if "?" in line or "请补充" in line or "需要补充" in line
        )
    )[:4]
    base_summary_parts = [part for part in [existing_summary.strip(), *user_lines[-3:]] if part]
    base_summary = "；".join(base_summary_parts[-4:]) or "该线程已累计若干轮与业务口径相关的问答。"
    return ThreadSummaryOutput(
        summary=base_summary,
        resolved_facts=resolved_facts,
        constraints=constraints,
        open_questions=open_questions,
    )


async def _llm_summary_output(
    *,
    existing_summary: str,
    turns: list[ThreadConversationTurn],
    settings: Settings,
) -> ThreadSummaryOutput:
    llm = ChatOpenAI(
        model=settings.sql_agent_chat_model,
        openai_api_key=settings.sql_agent_chat_api_key,
        openai_api_base=settings.sql_agent_chat_base_url,
        temperature=0,
        timeout=120,
        max_retries=1,
        extra_body={"enable_thinking": False},
    )
    transcript = "\n".join(
        f"{'用户' if turn.role == 'user' else '助手'}: {turn.content.strip()}"
        for turn in turns
        if turn.content.strip()
    )
    prompt = f"""
你正在为一个 Text-to-SQL 线程维护可迭代更新的滚动摘要。

请只返回 JSON，字段必须包含：
- summary
- resolved_facts
- constraints
- open_questions

要求：
- `summary` 使用中文，概括本批对话补充了哪些业务语义。
- `resolved_facts` 提炼已经明确的业务事实、字段映射、口径或偏好。
- `constraints` 只保留真正会影响 SQL 生成的约束。
- `open_questions` 只保留仍然悬而未决的关键问题。
- 不要重复逐字抄写原始对话。

已有滚动摘要：
{existing_summary or "(none)"}

本批新增对话：
{transcript}
"""
    message = await llm.ainvoke(prompt)
    return parse_model_output(ThreadSummaryOutput, content_to_text(message.content))


async def summarize_turn_batch(
    *,
    existing_summary: str,
    turns: list[ThreadConversationTurn],
    settings: Settings,
) -> str:
    """Create the next rolling summary from a compacted batch of old turns."""

    if not turns:
        return existing_summary.strip()
    if (
        settings.sql_agent_chat_api_key
        and settings.sql_agent_chat_base_url
        and settings.sql_agent_chat_model
    ):
        try:
            output = await _llm_summary_output(
                existing_summary=existing_summary,
                turns=turns,
                settings=settings,
            )
        except Exception:
            output = _heuristic_summary_output(existing_summary=existing_summary, turns=turns)
    else:
        output = _heuristic_summary_output(existing_summary=existing_summary, turns=turns)
    rendered = _render_structured_summary(
        summary=output.summary,
        resolved_facts=output.resolved_facts,
        constraints=output.constraints,
        open_questions=output.open_questions,
    )
    return _truncate(rendered, max(400, int(settings.sql_agent_thread_summary_char_budget)))


async def append_thread_turn(
    session: AsyncSession,
    *,
    datasource_id: str,
    thread_id: str,
    role: str,
    content: str,
    turn_metadata: dict[str, Any] | None = None,
) -> ThreadConversationTurn | None:
    """Persist a raw thread turn for later recall and compression."""

    cleaned = (content or "").strip()
    if not cleaned:
        return None
    row = ThreadConversationTurn(
        thread_id=thread_id,
        datasource_id=datasource_id,
        role=role.strip()[:16] or "assistant",
        content=cleaned,
        turn_metadata=turn_metadata,
    )
    session.add(row)
    await session.flush()
    return row


def build_recent_turn_context(turns: list[dict[str, str]]) -> str:
    """Render the most recent uncompressed turns into prompt text."""

    if not turns:
        return ""
    return "\n".join(
        f"{'用户' if turn['role'] == 'user' else '助手'}: {turn['content']}"
        for turn in turns
    )


async def load_runtime_thread_context(
    session: AsyncSession,
    *,
    datasource_id: str,
    thread_id: str | None,
    current_question: str,
    settings: Settings,
) -> ThreadContextWindow:
    """为 prepare_runtime 加载线程窗口：滚动摘要 + 尾部原始轮次。

    当总字符超 sql_agent_thread_context_char_budget 且轮次足够多时，
    将旧轮次 LLM 压缩进 rolling_summary，仅保留 tail_turns 条原文进 Agent。
    """

    if not datasource_id or not thread_id:
        return ThreadContextWindow(
            summary="",
            summary_status="empty",
            recent_turns=[],
            stored_turn_count=0,
            recent_turn_count=0,
            summarized_turn_count=0,
            compression_count=0,
            compression_applied=False,
        )

    row = await session.get(ThreadContextSummary, (thread_id, datasource_id))
    if row is None:
        row = ThreadContextSummary(
            thread_id=thread_id,
            datasource_id=datasource_id,
            rolling_summary="",
            summary_status="empty",
            summary_metadata={"last_compacted_turn_id": 0},
        )
        session.add(row)
        await session.flush()

    turns_result = await session.execute(
        select(ThreadConversationTurn)
        .where(ThreadConversationTurn.thread_id == thread_id)
        .where(ThreadConversationTurn.datasource_id == datasource_id)
        .order_by(ThreadConversationTurn.id.asc())
    )
    turns = list(turns_result.scalars().all())
    stored_turn_count = len(turns)
    tail_turns = max(2, int(settings.sql_agent_thread_context_tail_turns))
    max_chars = max(800, int(settings.sql_agent_thread_context_char_budget))
    min_turns = max(tail_turns + 1, int(settings.sql_agent_thread_context_compression_min_turns))
    total_chars = len(row.rolling_summary or "") + sum(len(turn.content or "") for turn in turns)

    metadata = dict(row.summary_metadata or {})
    last_compacted_turn_id = int(metadata.get("last_compacted_turn_id") or 0)
    compressible_turns = turns[:-tail_turns] if len(turns) > tail_turns else []
    new_turns_to_compact = [
        turn for turn in compressible_turns if int(turn.id) > last_compacted_turn_id
    ]

    # --- 超预算时压缩旧轮次进 rolling_summary，避免 Agent 上下文爆炸 ---
    compression_applied = False
    if stored_turn_count >= min_turns and total_chars > max_chars and new_turns_to_compact:
        row.rolling_summary = await summarize_turn_batch(
            existing_summary=row.rolling_summary or "",
            turns=new_turns_to_compact,
            settings=settings,
        )
        metadata["last_compacted_turn_id"] = int(new_turns_to_compact[-1].id)
        metadata["last_compacted_turn_count"] = len(new_turns_to_compact)
        row.summary_metadata = metadata
        row.summary_status = "compressed"
        row.summarized_turn_count = int(row.summarized_turn_count or 0) + len(new_turns_to_compact)
        row.compression_count = int(row.compression_count or 0) + 1
        row.last_compacted_at = datetime.now(timezone.utc)
        compression_applied = True
    elif not row.rolling_summary.strip():
        row.summary_status = "fresh" if turns else "empty"

    recent_turns = turns[-tail_turns:] if turns else []
    if recent_turns and current_question.strip():
        tail = recent_turns[-1]
        if tail.role == "user" and tail.content.strip() == current_question.strip():
            recent_turns = recent_turns[:-1]

    last_user = next((turn.content for turn in reversed(turns) if turn.role == "user"), None)
    last_assistant = next(
        (turn.content for turn in reversed(turns) if turn.role == "assistant"),
        None,
    )
    row.last_user_message = _excerpt(last_user or "", 500) or None
    row.last_assistant_message = _excerpt(last_assistant or "", 500) or None
    row.char_count = total_chars
    recent_turn_count = len(recent_turns)
    row.recent_turn_count = recent_turn_count
    row.summary_metadata = metadata
    await session.flush()

    return ThreadContextWindow(
        summary=row.rolling_summary or "",
        summary_status=row.summary_status,
        recent_turns=[
            {"role": turn.role, "content": turn.content}
            for turn in recent_turns
            if turn.content.strip()
        ],
        stored_turn_count=stored_turn_count,
        recent_turn_count=recent_turn_count,
        summarized_turn_count=int(row.summarized_turn_count or 0),
        compression_count=int(row.compression_count or 0),
        compression_applied=compression_applied,
    )


def render_assistant_turn_text(
    *,
    response_text: str | None,
    generated_sql: str | None,
    sql_explanation: str | None,
    sql_error: str | None,
    clarification_prompt: str | None = None,
) -> str:
    """Create one persistent assistant utterance from workflow outputs."""

    if clarification_prompt:
        return clarification_prompt.strip()
    if (response_text or "").strip():
        return response_text.strip()
    if (sql_error or "").strip():
        return f"SQL 生成已中止：{sql_error.strip()}"
    if (generated_sql or "").strip():
        if (sql_explanation or "").strip():
            return f"已生成 SQL。{sql_explanation.strip()}"
        return "已生成 SQL，可继续检查或执行。"
    return "本轮分析已完成。"
