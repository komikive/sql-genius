"""Workbench 对话 API：SSE 流式主链路 + 线程持久化 + 回合后学习。

核心入口：
- POST /chat/stream → _stream_chat_events（LangGraph astream + learning + done）
- GET  /chat/threads/{id}/turns → 历史回放 trace_steps
- POST /chat/threads/{id}/feedback → 后台 spawn 学习审查
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, get_db
from app.core.observability import trace_attributes, trace_content, trace_observation
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.thread_conversation_turn import ThreadConversationTurn
from app.services.history_audit import touch_admin_session
from app.services.learning_review import run_post_turn_learning_review, spawn_post_turn_learning_review
from app.services.datasource_resolve import list_resolved_datasources
from app.services.thread_context import append_thread_turn, render_assistant_turn_text

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatStreamRequest(BaseModel):
    """Client message for a workflow thread."""

    thread_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    datasource_id: str | None = Field(default=None, min_length=1)
    resume: bool = Field(
        default=False,
        description="When true, `message` is treated as a resume payload for a pending interrupt.",
    )


def _json_dumps(obj: object) -> str:
    """序列化 SSE 负载，并保留中文原文。"""
    return json.dumps(obj, default=str, ensure_ascii=False)


def _safe_stream_error(exc: Exception) -> str:
    """把异常压成可通过 SSE 返回的短单行错误信息。"""
    raw = str(exc).strip().replace("\n", " ")
    if not raw:
        return type(exc).__name__
    if len(raw) > 240:
        return raw[:237] + "..."
    return raw


def _truncate_trace_value(value: Any, *, depth: int = 0) -> Any:
    """限制 trace 负载大小，避免前端展示和历史落库被大对象撑爆。"""
    if depth > 4:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) <= 1200:
            return text
        return text[:1199] + "…"
    if isinstance(value, list):
        return [
            _truncate_trace_value(item, depth=depth + 1)
            for item in value[:12]
        ]
    if isinstance(value, dict):
        trimmed: dict[str, Any] = {}
        for idx, (key, inner) in enumerate(value.items()):
            if idx >= 20:
                break
            trimmed[str(key)] = _truncate_trace_value(inner, depth=depth + 1)
        return trimmed
    return str(value)


def _sanitize_trace_step(chunk: object) -> dict[str, Any] | None:
    """只接收字典形式的 LangGraph 自定义事件作为可记录 trace。"""
    if not isinstance(chunk, dict):
        return None
    return _truncate_trace_value(chunk)  # type: ignore[return-value]


async def _try_touch_session(
    *,
    thread_id: str,
    user_message: str,
    increment_turn: bool = True,
) -> None:
    """尽力更新历史会话摘要；审计失败不应该影响主聊天流程。"""
    try:
        async with AsyncSessionLocal() as session:
            await touch_admin_session(
                session,
                thread_id=thread_id,
                user_message=user_message,
                increment_turn=increment_turn,
            )
            await session.commit()
    except Exception:
        # History/audit writes must not break the thesis chat flow.
        return


async def _resolve_effective_datasource(datasource_id: str | None) -> str | None:
    """优先使用显式数据源；未传入时回退到默认或第一个可用数据源。"""
    explicit = (datasource_id or "").strip() or None
    if explicit:
        return explicit
    try:
        async with AsyncSessionLocal() as session:
            candidates = await list_resolved_datasources(session, get_settings())
            default_item = next((item for item in candidates if item.is_default), None)
            if default_item is not None:
                return default_item.id
            if candidates:
                return candidates[0].id
    except Exception:
        return None
    return None


async def _get_thread_bound_datasource(thread_id: str) -> str | None:
    """读取当前线程首轮对话绑定的数据源。"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ThreadConversationTurn.datasource_id)
                .where(ThreadConversationTurn.thread_id == thread_id)
                .order_by(ThreadConversationTurn.id.asc())
                .limit(1)
            )
            return result.scalar_one_or_none()
    except Exception:
        return None


async def _enforce_thread_datasource_binding(thread_id: str, datasource_id: str | None) -> str | None:
    """防止同一个会话线程在后续轮次里静默切换数据源。"""
    bound_datasource_id = await _get_thread_bound_datasource(thread_id)
    if bound_datasource_id is None:
        return datasource_id
    if datasource_id is None:
        return bound_datasource_id
    if datasource_id != bound_datasource_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "thread_datasource_mismatch",
                "message": "This thread is already bound to another datasource and cannot be switched.",
                "details": {
                    "thread_id": thread_id,
                    "bound_datasource_id": bound_datasource_id,
                    "requested_datasource_id": datasource_id,
                },
            },
        )
    return bound_datasource_id


async def _try_append_thread_turn(
    *,
    datasource_id: str | None,
    thread_id: str,
    role: str,
    content: str,
    turn_metadata: dict[str, object] | None = None,
) -> ThreadConversationTurn | None:
    """尽力持久化单轮对话；落库失败时不打断 SSE 流。"""
    if not datasource_id:
        return None
    try:
        async with AsyncSessionLocal() as session:
            row = await append_thread_turn(
                session,
                datasource_id=datasource_id,
                thread_id=thread_id,
                role=role,
                content=content,
                turn_metadata=turn_metadata,
            )
            await session.commit()
            return row
    except Exception:
        return None


async def _stream_chat_events(
    request: Request,
    body: ChatStreamRequest,
) -> AsyncIterator[bytes]:
    """执行 LangGraph 工作流，并把输出转换成前端可消费的 SSE 事件。

    事件类型：
    - step: 可观测 trace（含图节点 custom 事件与学习审查 memory_autoupdate）
    - interrupt: 人机澄清，客户端下一轮需带 resume=true
    - update: LangGraph state 增量（调试/扩展用）
    - done: 本轮结束，携带 assistant 文本与 SQL 元数据

    持久化策略：session/turn 写入失败不中断 SSE；学习审查在 done 之前同步执行，
    以便 Workbench 时间线能立即展示主记忆/QA 沉淀结果。
    """
    graph = request.app.state.workflow
    user_message = body.message.strip()

    # --- 1. 数据源与线程约束 ---
    effective_datasource_id = await _resolve_effective_datasource(body.datasource_id)
    effective_datasource_id = await _enforce_thread_datasource_binding(
        body.thread_id,
        effective_datasource_id,
    )
    # 澄清中断时从 interrupt 事件提取 prompt，用于拼 assistant 展示文案
    latest_interrupt_prompt: str | None = None

    # 尽早落库用户轮次，避免图执行失败时侧栏/历史完全缺失
    await _try_touch_session(thread_id=body.thread_id, user_message=user_message)
    await _try_append_thread_turn(
        datasource_id=effective_datasource_id,
        thread_id=body.thread_id,
        role="user",
        content=user_message,
        turn_metadata={"resume": body.resume},
    )

    # --- 2. 构造 LangGraph 输入 ---
    # thread_id 绑定 checkpointer，支持同会话多轮与 interrupt/resume
    config = {"configurable": {"thread_id": body.thread_id}}
    payload: object = (
        Command(resume=body.message)
        if body.resume
        else {
            "datasource_id": effective_datasource_id,
            "thread_id": body.thread_id,
            "user_question": user_message,
        }
    )
    # 清洗后的 trace 副本，最终写入 assistant turn_metadata 供历史回放
    trace_steps: list[dict[str, Any]] = []

    def _record_trace_step(step_payload: dict[str, Any]) -> bytes:
        """保存一份清洗后的 trace，同时返回对应的 SSE 帧（实时 payload 不裁剪）。"""
        sanitized_step = _sanitize_trace_step(step_payload)
        if sanitized_step is not None:
            trace_steps.append(sanitized_step)
        return f"event: step\ndata: {_json_dumps(step_payload)}\n\n".encode()

    try:
        # --- 3. 流式执行工作流 ---
        # custom: 节点内 get_stream_writer() 推送（Agent 工具、推理摘要等）
        # updates: 节点 state 变更；含 __interrupt__ 时表示需要用户补充信息
        async for mode, chunk in graph.astream(
            payload,
            config,
            stream_mode=["updates", "custom"],
        ):
            if mode == "custom":
                sanitized_step = _sanitize_trace_step(chunk)
                if sanitized_step is not None:
                    trace_steps.append(sanitized_step)
                yield f"event: step\ndata: {_json_dumps(chunk)}\n\n".encode()
            elif mode == "updates" and isinstance(chunk, dict):
                if "__interrupt__" in chunk:
                    for intr in chunk["__interrupt__"]:
                        body_out = {"interrupt_id": intr.id, "value": intr.value}
                        if isinstance(intr.value, dict):
                            prompt = intr.value.get("prompt")
                            if isinstance(prompt, str) and prompt.strip():
                                latest_interrupt_prompt = prompt.strip()
                        yield (
                            f"event: interrupt\ndata: {_json_dumps(body_out)}\n\n"
                        ).encode()
                else:
                    yield f"event: update\ndata: {_json_dumps(chunk)}\n\n".encode()

        # --- 4. 读取 checkpointer 中的最终 state ---
        final_values: dict[str, object] = {}
        try:
            snapshot = await graph.aget_state(config)
            if hasattr(snapshot, "values") and isinstance(snapshot.values, dict):
                final_values = snapshot.values
        except Exception:
            final_values = {}

        # 澄清 resume 后 user_question 可能在图内被合并，以 state 为准
        effective_datasource_id = (
            str(final_values.get("datasource_id")).strip()
            if isinstance(final_values.get("datasource_id"), str)
            else effective_datasource_id
        )
        resolved_user_question = (
            str(final_values.get("user_question")).strip()
            if isinstance(final_values.get("user_question"), str)
            else user_message
        )
        assistant_text = render_assistant_turn_text(
            response_text=(
                str(final_values.get("response_text"))
                if isinstance(final_values.get("response_text"), str)
                else None
            ),
            generated_sql=(
                str(final_values.get("generated_sql"))
                if isinstance(final_values.get("generated_sql"), str)
                else None
            ),
            sql_explanation=(
                str(final_values.get("sql_explanation"))
                if isinstance(final_values.get("sql_explanation"), str)
                else None
            ),
            sql_error=(
                str(final_values.get("sql_error"))
                if isinstance(final_values.get("sql_error"), str)
                else None
            ),
            clarification_prompt=latest_interrupt_prompt,
        )

        # --- 5. 回合后学习（同步进 SSE，在 done 之前）---
        # 澄清中断或未完成时不沉淀；与 submit_turn_feedback 的后台学习不同
        learning_result = None
        if (
            effective_datasource_id
            and not latest_interrupt_prompt
            and final_values.get("status") == "completed"
        ):
            try:
                async with AsyncSessionLocal() as session:
                    learning_result = await run_post_turn_learning_review(
                        session,
                        datasource_id=effective_datasource_id,
                        thread_id=body.thread_id,
                        user_question=resolved_user_question,
                        assistant_text=assistant_text,
                        generated_sql=(
                            str(final_values.get("generated_sql"))
                            if isinstance(final_values.get("generated_sql"), str)
                            else None
                        ),
                        sql_explanation=(
                            str(final_values.get("sql_explanation"))
                            if isinstance(final_values.get("sql_explanation"), str)
                            else None
                        ),
                        activated_skill_pack_names=[
                            str(item)
                            for item in (final_values.get("activated_skill_pack_names") or [])
                            if isinstance(item, str)
                        ]
                        if isinstance(final_values.get("activated_skill_pack_names"), list)
                        else [],
                        sql_execution_success=bool(final_values.get("sql_execution_success")),
                        settings=get_settings(),
                    )
                    await session.commit()
            except Exception as exc:
                yield _record_trace_step(
                    {
                        "step_id": "memory_autoupdate",
                        "phase": "error",
                        "error": _safe_stream_error(exc),
                    }
                )
            else:
                memory_count = learning_result.memory_count if learning_result is not None else 0
                qa_example_count = learning_result.qa_example_count if learning_result is not None else 0
                updates = learning_result.memory_updates if learning_result is not None else []
                if updates:
                    change_labels = [
                        f"{'改写' if item.get('action') == 'replaced' else '新增'} {item.get('title')}"
                        for item in updates
                        if str(item.get("title") or "").strip()
                    ]
                    summary = (
                        f"本轮自动学习结果：主记忆 {memory_count} 条、QA 案例 {qa_example_count} 条。"
                        + (
                            f" 已维护主记忆：{'；'.join(change_labels[:4])}"
                            if change_labels
                            else ""
                        )
                    )
                else:
                    summary = (
                        f"本轮自动学习结果：主记忆 {memory_count} 条、QA 案例 {qa_example_count} 条。"
                    )
                yield _record_trace_step(
                    {
                        "step_id": "memory_autoupdate",
                        "phase": "complete",
                        "memory_count": memory_count,
                        "qa_example_count": qa_example_count,
                        "updates": updates,
                        "signal_buffered": (
                            learning_result.signal_buffered if learning_result is not None else False
                        ),
                        "summary": summary,
                    }
                )

        # --- 6. 持久化 assistant 轮次（含 trace_steps 供历史还原）---
        assistant_row = await _try_append_thread_turn(
            datasource_id=effective_datasource_id,
            thread_id=body.thread_id,
            role="assistant",
            content=assistant_text,
            turn_metadata={
                "status": final_values.get("status"),
                "has_sql": bool(final_values.get("generated_sql")),
                "clarification": bool(latest_interrupt_prompt),
                "generated_sql": (
                    str(final_values.get("generated_sql"))
                    if isinstance(final_values.get("generated_sql"), str)
                    else None
                ),
                "sql_explanation": (
                    str(final_values.get("sql_explanation"))
                    if isinstance(final_values.get("sql_explanation"), str)
                    else None
                ),
                "sql_error": (
                    str(final_values.get("sql_error"))
                    if isinstance(final_values.get("sql_error"), str)
                    else None
                ),
                "sql_execution_success": bool(final_values.get("sql_execution_success")),
                "tool_calls_made": [
                    str(item)
                    for item in (final_values.get("tool_calls_made") or [])
                    if isinstance(item, str)
                ]
                if isinstance(final_values.get("tool_calls_made"), list)
                else [],
                "activated_skill_pack_names": [
                    str(item)
                    for item in (final_values.get("activated_skill_pack_names") or [])
                    if isinstance(item, str)
                ]
                if isinstance(final_values.get("activated_skill_pack_names"), list)
                else [],
                "recalled_memory_titles": [
                    str(item)
                    for item in (final_values.get("recalled_memory_titles") or [])
                    if isinstance(item, str)
                ]
                if isinstance(final_values.get("recalled_memory_titles"), list)
                else [],
                "trace_steps": trace_steps,
            },
        )
        # 更新会话摘要时间戳，不再重复计数 turn
        await _try_touch_session(
            thread_id=body.thread_id,
            user_message=user_message,
            increment_turn=False,
        )

        # --- 7. 发送 done，通知前端结束本轮流式渲染 ---
        done_payload = {
            "ok": True,
            "assistant_turn_id": int(assistant_row.id) if assistant_row else None,
            "response_text": assistant_text,
            "generated_sql": (
                str(final_values.get("generated_sql"))
                if isinstance(final_values.get("generated_sql"), str)
                else None
            ),
            "sql_explanation": (
                str(final_values.get("sql_explanation"))
                if isinstance(final_values.get("sql_explanation"), str)
                else None
            ),
            "sql_execution_success": bool(final_values.get("sql_execution_success")),
            "activated_skill_pack_names": [
                str(item)
                for item in (final_values.get("activated_skill_pack_names") or [])
                if isinstance(item, str)
            ]
            if isinstance(final_values.get("activated_skill_pack_names"), list)
            else [],
            "trace_step_count": len(trace_steps),
        }
        yield f"event: done\ndata: {_json_dumps(done_payload)}\n\n".encode()
    except Exception as exc:
        # 保证客户端总能收到结束帧，避免 Workbench 一直 loading
        await _try_touch_session(
            thread_id=body.thread_id,
            user_message=user_message,
            increment_turn=False,
        )
        yield (
            f"event: done\ndata: {_json_dumps({'ok': False, 'error': _safe_stream_error(exc)})}\n\n"
        ).encode()


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatStreamRequest) -> StreamingResponse:
    if getattr(request.app.state, "workflow", None) is None:
        raise HTTPException(status_code=503, detail="workflow_unavailable")

    guard = request.app.state.thread_run_guard
    if not await guard.try_acquire(body.thread_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "thread_busy",
                "message": "This thread already has an active Agent run.",
            },
        )

    async def guarded_events() -> AsyncIterator[bytes]:
        try:
            with trace_attributes(
                thread_id=body.thread_id,
                datasource_id=body.datasource_id,
            ):
                with trace_observation(
                    "process-chat-turn",
                    as_type="agent",
                    input={"message": body.message},
                    input_summary={
                        "message_chars": len(body.message),
                        "resume": body.resume,
                    },
                    metadata={
                        "thread_id": body.thread_id,
                        "datasource_id": body.datasource_id,
                        "resume": body.resume,
                    },
                ) as request_span:
                    done_payload: dict[str, Any] | None = None
                    async for event in _stream_chat_events(request, body):
                        if event.startswith(b"event: done\n"):
                            try:
                                done_payload = json.loads(event.split(b"data: ", 1)[1])
                            except (IndexError, json.JSONDecodeError, UnicodeDecodeError):
                                done_payload = None
                        yield event
                    if request_span is not None and done_payload is not None:
                        safe_output = {
                            "ok": bool(done_payload.get("ok")),
                            "has_sql": bool(done_payload.get("generated_sql")),
                            "trace_step_count": done_payload.get("trace_step_count", 0),
                        }
                        request_span.update(
                            output=trace_content(
                                {
                                    "response_text": done_payload.get("response_text"),
                                    "generated_sql": done_payload.get("generated_sql"),
                                },
                                fallback=safe_output,
                            ),
                            level="DEFAULT" if safe_output["ok"] else "ERROR",
                            status_message=(
                                None if safe_output["ok"] else str(done_payload.get("error") or "failed")
                            ),
                        )
        finally:
            await guard.release(body.thread_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        guarded_events(),
        media_type="text/event-stream",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Suggested questions (LLM-powered, scoped to a datasource)
# ---------------------------------------------------------------------------

import time as _time

_SUGGESTION_PROMPT_TEMPLATE = """\
你是一个 Text-to-SQL 智能助手。根据下面的数据源信息，为用户生成 {count} 个自然语言查询建议。
要求：
- 每个建议应该是一句完整的中文业务问题
- 问题应该覆盖不同的分析角度（聚合、排名、趋势、筛选等）
- 问题应该与该数据源的表结构和业务场景紧密相关
- 只能基于提供的数据源概述和表结构摘要来提问，不要虚构年份、季度、具体原因值、供应商名称、状态值或业务枚举
- 如果没有足够信息支撑具体枚举，请改用更稳妥的相对时间和通用分析口径，例如“近 30 天”“按类型”“按区域”“按状态”
- 优先生成适合直接做 SQL 分析的问题，而不是需要额外业务上下文解释的问题
- 直接返回 JSON 数组，不要额外解释

数据源概述：
{summary}

表结构摘要：
{schema_excerpt}

返回格式：["问题1", "问题2", ...]"""

_FALLBACK_SUGGESTIONS = [
    "统计近 30 天的数据变化趋势",
    "列出金额最高的前 10 条记录",
    "按类别汇总并对比各项指标",
]

_FAST_MODEL_FALLBACK = "qwen3.5-flash"
_SUGGESTION_CACHE: dict[str, tuple[float, list[str]]] = {}
_SUGGESTION_CACHE_TTL = 600  # 10 minutes


class SuggestionsResponse(BaseModel):
    items: list[str]
    datasource_id: str | None = None
    is_fallback: bool = False


def _coerce_suggestion_items(raw: str, count: int) -> list[str]:
    """容错解析模型返回的推荐问题，即使它不是严格 JSON。"""
    text = (raw or "").strip()
    if not text:
        return []

    def _clean(items: list[Any]) -> list[str]:
        cleaned: list[str] = []
        for item in items:
            if not isinstance(item, str):
                continue
            cooked = item.strip().lstrip("-•1234567890.、 ").strip()
            if cooked:
                cleaned.append(cooked)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in cleaned:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped[:count]

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return _clean(parsed)
    except Exception:
        pass

    if "[" in text and "]" in text:
        candidate = text[text.find("[") : text.rfind("]") + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return _clean(parsed)
        except Exception:
            pass

    quoted = re.findall(r'"([^"\n]+)"', text)
    if quoted:
        return _clean(quoted)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return _clean(lines)


def _schema_excerpt(payload: dict | None, char_limit: int = 1200) -> str:
    """把 schema 快照压缩成推荐问题 prompt 可用的简短摘要。"""
    if not payload:
        return "(无 schema 信息)"
    tables = payload.get("tables") or payload.get("schemas", {})
    if isinstance(tables, list):
        lines = []
        for t in tables[:15]:
            name = t.get("name") or t.get("table_name", "?")
            cols = t.get("columns", [])
            col_names = [c.get("name", "?") for c in cols[:8]] if isinstance(cols, list) else []
            lines.append(f"- {name}({', '.join(col_names)})")
        return "\n".join(lines)[:char_limit]
    if isinstance(tables, dict):
        lines = []
        for schema_name, tbl_list in list(tables.items())[:5]:
            if isinstance(tbl_list, list):
                for t in tbl_list[:10]:
                    name = t.get("name") or t.get("table_name", "?")
                    cols = t.get("columns", [])
                    col_names = [c.get("name", "?") for c in cols[:8]] if isinstance(cols, list) else []
                    lines.append(f"- {schema_name}.{name}({', '.join(col_names)})")
        return "\n".join(lines)[:char_limit]
    return str(tables)[:char_limit]


def _table_names_from_payload(payload: dict | None) -> set[str]:
    """从扁平或按 schema 分组的快照结构中提取表名集合。"""
    if not payload:
        return set()
    tables = payload.get("tables") or payload.get("schemas", {})
    names: set[str] = set()
    if isinstance(tables, list):
        for item in tables:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("table_name") or "").strip()
                if name:
                    names.add(name)
        return names
    if isinstance(tables, dict):
        for tbl_list in tables.values():
            if isinstance(tbl_list, list):
                for item in tbl_list:
                    if isinstance(item, dict):
                        name = str(item.get("name") or item.get("table_name") or "").strip()
                        if name:
                            names.add(name)
    return names


def _grounded_fallback_suggestions(
    datasource_id: str | None,
    summary: str,
    schema_payload: dict | None,
    count: int,
) -> list[str]:
    """当模型不可用或输出不可靠时，生成稳定的演示级推荐问题。"""
    table_names = _table_names_from_payload(schema_payload)

    if {"plants", "production_lines", "machines", "work_orders", "downtime_events"}.issubset(table_names):
        return [
            "哪些产线的计划产量与实际产量差距最大？",
            "哪些机器累计停机损失时间最高？",
            "各工厂的能耗和碳排放总量排名如何？",
            "当前工单状态分布是怎样的？",
            "哪些机器的维修成本最高？",
            "从传感器读数质量看，哪类 sensor 的异常读数更多？",
        ][:count]

    if {"hospitals", "patients", "encounters", "claims", "claim_lines"}.issubset(table_names):
        return [
            "按付款方统计，当前各自的 claim 数量、总申报金额、总支付金额、总拒付金额分别是多少？",
            "哪个科室的拒付金额最高？",
            "当前 prior authorization 的状态分布是怎样的？",
            "不同就诊类型的平均收费金额和平均认可金额分别是多少？",
            "高风险患者是否有更多未关闭的 care management 事件？",
            "哪些付款方的拒付金额占比更高？",
        ][:count]

    if {"stores", "products", "customers", "orders", "order_items"}.issubset(table_names):
        return [
            "按大区统计当前净销售额排名如何？",
            "哪些门店的净销售额最高？",
            "哪些商品类目带来的净销售额最高？",
            "哪个区域的订单退货率最高？",
            "不同会员等级贡献的订单量和净销售额分别是多少？",
            "不同促销活动带来的订单量和净销售额表现如何？",
        ][:count]

    if "制造" in summary or "工单" in summary or "传感器" in summary:
        return [
            "哪些产线的计划产量与实际产量差距最大？",
            "哪些机器累计停机损失时间最高？",
            "各工厂的能耗和碳排放总量排名如何？",
            "当前工单状态分布是怎样的？",
        ][:count]

    if "医疗" in summary or "理赔" in summary or "患者" in summary:
        return [
            "按付款方统计当前理赔数量、支付金额和拒付金额。",
            "哪个科室的拒付金额最高？",
            "当前 prior authorization 的状态分布是怎样的？",
            "高风险患者是否有更多未关闭的护理事件？",
        ][:count]

    if "零售" in summary or "订单" in summary or "门店" in summary:
        return [
            "按大区统计当前净销售额排名如何？",
            "哪些门店的净销售额最高？",
            "哪些商品类目带来的净销售额最高？",
            "哪个区域的订单退货率最高？",
        ][:count]

    return _FALLBACK_SUGGESTIONS[:count]


def _suggestions_need_grounded_fallback(items: list[str]) -> bool:
    """识别过泛、疑似幻觉或细节过度编造的推荐问题。"""
    if not items:
        return True
    generic_hits = 0
    for item in items:
        text = item.strip()
        if not text:
            return True
        if re.search(r"\b20\d{2}\b", text):
            return True
        if re.search(r"Q[1-4]|第[一二三四]季度|上季度|下季度", text):
            return True
        if any(ch in text for ch in ("'", '"', "“", "”", "‘", "’")):
            return True
        if any(phrase in text for phrase in _FALLBACK_SUGGESTIONS):
            generic_hits += 1
    return generic_hits >= max(1, len(items) // 2)


@router.get("/chat/suggestions", response_model=SuggestionsResponse)
async def get_chat_suggestions(
    datasource_id: str | None = Query(default=None),
    count: int = Query(default=4, ge=1, le=8),
    session: AsyncSession = Depends(get_db),
) -> SuggestionsResponse:
    settings = get_settings()
    grounded_fallback = _grounded_fallback_suggestions(datasource_id, "", None, count)
    if not (
        settings.sql_agent_chat_api_key
        and settings.sql_agent_chat_base_url
        and settings.sql_agent_chat_model
    ):
        return SuggestionsResponse(items=grounded_fallback, datasource_id=datasource_id, is_fallback=True)

    cache_key = f"{datasource_id or ''}:{count}"
    cached = _SUGGESTION_CACHE.get(cache_key)
    if cached:
        ts, items = cached
        if _time.time() - ts < _SUGGESTION_CACHE_TTL:
            return SuggestionsResponse(items=items, datasource_id=datasource_id, is_fallback=False)

    summary = ""
    schema_payload: dict | None = None

    if datasource_id:
        profile = await session.get(DatasourceProfile, datasource_id)
        if profile:
            summary = profile.summary or ""
        snapshot = await session.get(DatasourceSchemaSnapshot, datasource_id)
        if snapshot:
            schema_payload = snapshot.payload

    if not summary and not schema_payload:
        return SuggestionsResponse(items=grounded_fallback, datasource_id=datasource_id, is_fallback=True)

    grounded_fallback = _grounded_fallback_suggestions(datasource_id, summary, schema_payload, count)

    try:
        from langchain_openai import ChatOpenAI

        fast_model = settings.sql_agent_suggestion_model or _FAST_MODEL_FALLBACK
        llm = ChatOpenAI(
            model=fast_model,
            openai_api_key=settings.sql_agent_chat_api_key,
            openai_api_base=settings.sql_agent_chat_base_url,
            temperature=0.8,
            max_tokens=512,
            timeout=15,
            extra_body={"enable_thinking": False},
        )
        prompt_text = _SUGGESTION_PROMPT_TEMPLATE.format(
            count=count,
            summary=summary[:600],
            schema_excerpt=_schema_excerpt(schema_payload),
        )
        result = await llm.ainvoke(prompt_text)
        raw = result.content if hasattr(result, "content") else str(result)
        if isinstance(raw, str):
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result_items = _coerce_suggestion_items(raw, count)
            if result_items and not _suggestions_need_grounded_fallback(result_items):
                _SUGGESTION_CACHE[cache_key] = (_time.time(), result_items)
                return SuggestionsResponse(items=result_items, datasource_id=datasource_id, is_fallback=False)
            if result_items:
                logger.info("Suggestion generator produced low-grounding prompts; using schema-grounded fallback")
    except Exception:
        logger.warning("Failed to generate LLM suggestions, using fallback", exc_info=True)

    return SuggestionsResponse(items=grounded_fallback, datasource_id=datasource_id, is_fallback=True)


# ---------------------------------------------------------------------------
# Thread conversation turns (load past conversations)
# ---------------------------------------------------------------------------

class ThreadTurnResponse(BaseModel):
    id: int
    datasource_id: str
    role: str
    content: str
    turn_metadata: dict | None = None
    created_at: str | None = None


class ThreadTurnsListResponse(BaseModel):
    thread_id: str
    items: list[ThreadTurnResponse]


@router.get("/chat/threads/{thread_id}/turns", response_model=ThreadTurnsListResponse)
async def get_thread_turns(
    thread_id: str,
    session: AsyncSession = Depends(get_db),
) -> ThreadTurnsListResponse:
    result = await session.execute(
        select(ThreadConversationTurn)
        .where(ThreadConversationTurn.thread_id == thread_id)
        .order_by(ThreadConversationTurn.id.asc())
        .limit(200)
    )
    rows = result.scalars().all()
    return ThreadTurnsListResponse(
        thread_id=thread_id,
        items=[
            ThreadTurnResponse(
                id=row.id,
                datasource_id=row.datasource_id,
                role=row.role,
                content=row.content,
                turn_metadata=row.turn_metadata,
                created_at=str(row.created_at) if row.created_at else None,
            )
            for row in rows
        ],
    )


# ---------------------------------------------------------------------------
# Turn feedback (thumbs up/down + save-to-skill)
# ---------------------------------------------------------------------------


class TurnFeedbackRequest(BaseModel):
    rating: Literal["positive", "negative"]
    save_to_skill: bool = False
    comment: str | None = None


class TurnFeedbackResponse(BaseModel):
    ok: bool
    turn_id: int
    rating: str
    learning_triggered: bool = False


@router.post(
    "/chat/threads/{thread_id}/turns/{turn_id}/feedback",
    response_model=TurnFeedbackResponse,
)
async def submit_turn_feedback(
    thread_id: str,
    turn_id: int,
    body: TurnFeedbackRequest,
    session: AsyncSession = Depends(get_db),
) -> TurnFeedbackResponse:
    turn = await session.execute(
        select(ThreadConversationTurn)
        .where(ThreadConversationTurn.thread_id == thread_id)
        .where(ThreadConversationTurn.id == turn_id)
        .limit(1)
    )
    row = turn.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="turn_not_found")

    row.feedback_rating = body.rating
    row.feedback_comment = body.comment
    row.feedback_at = datetime.now(timezone.utc)
    await session.flush()

    learning_triggered = False

    if body.rating == "positive" or body.save_to_skill:
        metadata = row.turn_metadata or {}
        user_turn_row = await session.execute(
            select(ThreadConversationTurn)
            .where(ThreadConversationTurn.thread_id == thread_id)
            .where(ThreadConversationTurn.role == "user")
            .where(ThreadConversationTurn.id < row.id)
            .order_by(ThreadConversationTurn.id.desc())
            .limit(1)
        )
        user_turn = user_turn_row.scalars().first()
        user_question = user_turn.content if user_turn else ""

        if user_question and row.content:
            spawn_post_turn_learning_review(
                datasource_id=row.datasource_id,
                thread_id=thread_id,
                user_question=user_question,
                assistant_text=row.content,
                generated_sql=metadata.get("generated_sql") if isinstance(metadata, dict) else None,
                sql_explanation=metadata.get("sql_explanation") if isinstance(metadata, dict) else None,
                activated_skill_pack_names=(
                    metadata.get("activated_skill_pack_names", [])
                    if isinstance(metadata, dict)
                    else []
                ),
                sql_execution_success=(
                    bool(metadata.get("sql_execution_success"))
                    if isinstance(metadata, dict)
                    else False
                ),
                user_feedback_positive=(body.rating == "positive"),
                save_to_skill=body.save_to_skill,
            )
            learning_triggered = True

    await session.commit()
    return TurnFeedbackResponse(
        ok=True,
        turn_id=turn_id,
        rating=body.rating,
        learning_triggered=learning_triggered,
    )
