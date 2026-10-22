"""
Autonomous database agent runtime.

Architecture references:
- deepagents: Agent + Tool Loop pattern (not fixed StateGraph nodes).
  The LLM drives control flow by choosing tools; the harness provides
  iteration budget, large-result handling, and error recovery.
- hermes-agent: IterationBudget, background review, memory nudge,
  tool result → JSON error strings (not exceptions).

The runtime is a fully autonomous agent that can introspect schema,
run queries, search skills/memory/history, and save learned knowledge.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.observability import trace_content, trace_observation, usage_details_from_message
from app.core.llm_structured import content_to_text
from app.core.prompt_clock import build_prompt_clock_context
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.skill_pack import SkillPack
from app.services.agent_tools import build_agent_tools
from app.services.thread_context import build_recent_turn_context

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGENT_STEPS = 15
DEFAULT_BUDGET_WARNING_THRESHOLD = 12
_RETRIEVER_TOOL_NAMES = {
    "introspect_schema",
    "search_qa_examples",
    "search_history",
    "recall_memory",
    "search_skills",
    "search_skill_documents",
}


SYSTEM_PROMPT = """\
你是一个自主数据库智能助手，可以自由使用工具来回答用户关于数据的任何问题。

## 核心能力
- 查看数据库表结构（introspect_schema）
- 执行 SQL 查询并获取真实数据（execute_query）
- 搜索技能包定位相关技能（search_skills）
- 读取技能的统一主文档获取业务方法、字段口径和易错点（search_skill_documents）
- 搜索独立 QA 示例获取参考问法与 SQL（search_qa_examples）— 结构化沉淀案例，优先查阅
- 检索数据源记忆获取历史经验（recall_memory）
- 搜索历史对话与既往成功 SQL（search_history）— 会话级成功案例，演示与复用同等重要
- 将稳定全局知识写入数据源主记忆（save_memory）

## 工作方式
你是一个自主 Agent，不是简单的 SQL 生成器。你应该：
1. 理解用户意图 — 可能是数据查询、数据分析、表结构探索、或业务理解
2. **先检索可复用经验** — 对涉及业务指标、统计口径、SQL 写法的问题，在写 SQL 之前先查 QA 示例与历史成功案例
3. 主动获取需要的上下文 — 查看 schema、搜索技能包、检索记忆
4. 生成并验证 SQL — 确保使用正确的表名和列名
5. 可以执行查询获取真实结果 — 不只是生成 SQL
6. 如果确实发现长期稳定、可跨会话复用的全局知识，可以调用 save_memory 直接写入主记忆，但必须非常克制

## 检索顺序（数据/SQL 类问题务必遵守）
当用户问题涉及查数、指标、报表、趋势、排名、明细、关联等业务查询时，在调用 introspect_schema 或 execute_query **之前**，按顺序完成：
1. **search_qa_examples** — 查找结构化 QA 案例（问法 + SQL + 备注），有命中则优先对齐写法
2. **search_history** — 查找本数据源过往成功对话与 SQL，避免重复摸索
3. recall_memory / search_skills / search_skill_documents — 按需补充记忆与技能主文档
若上下文里已有「预检索参考」，仍需阅读并在回复中体现你是否参考了 QA/历史；必要时可再次调用工具核对。

## 重要规则
- 总是先确认表名和列名的正确性（用 introspect_schema）再写 SQL
- SQL 只允许 SELECT 查询，禁止任何修改操作
- 如果用户问题模糊，直接用中文请求澄清
- 对复杂业务问题，先查看当前上下文中的“可用技能目录”；如果某个技能明显匹配，优先用 search_skill_documents 读取该技能主文档
- 如果技能目录无法判断，再用 search_skills 检索；不要只凭技能名称直接回答复杂问题
- QA 示例与历史对话是**一等公民**知识源，不要跳过；即使技能包很少，也要先 search_qa_examples 再 search_history
- 记忆用于补充已验证经验；技能主文档用于确认业务方法、字段口径和易错点
- 不要在一次回答中调用太多工具 — 但检索类工具（search_qa_examples、search_history）不应省略
- 所有面向用户的文本都用中文
- 在调用工具前，可以先给出一句简短中文进度说明，说明你接下来要验证什么；不要输出冗长的内部推理
- 当你完成任务后，在最终回复中包含你的分析过程和结论
- save_memory 只适用于极少量高价值长期知识，不要保存临时结果、示例问答或一次性查询结论
- 系统消息会附带「当前参考时间」；用户说「今天」「本周」「近 N 天」等相对时间时，必须按该时间换算 SQL 条件，不要臆测日期

## 回复格式
最终回复（不调用任何工具时）应该是自然的中文对话，包含：
- 对用户问题的回答
- 如果生成了 SQL，包含 SQL 代码块
- 如果执行了查询，解释数据含义
- 如果需要澄清，说明需要什么信息"""

_TIME_BASE_BLOCK = """\
## 时间基准
{clock}
用户问题中的「今天」「昨天」「本周」「本月」「今年」「近 N 天」等相对时间表述，一律按该参考时间换算为 SQL 过滤条件；不要臆测其他日期。"""


def _build_system_message(settings: Settings) -> str:
    """System prompt with a fresh wall-clock anchor (refreshed before each LLM call)."""
    clock = build_prompt_clock_context(settings=settings)
    return f"{SYSTEM_PROMPT}\n\n{_TIME_BASE_BLOCK.format(clock=clock)}"


def _format_schema_overview(payload: dict | None, limit: int = 2000) -> str:
    """Compact DDL-like overview from schema snapshot."""
    if not payload:
        return ""
    tables = payload.get("tables") or []
    if not isinstance(tables, list):
        schemas = payload.get("schemas", {})
        if isinstance(schemas, dict):
            flat: list[dict] = []
            for tbl_list in schemas.values():
                if isinstance(tbl_list, list):
                    flat.extend(tbl_list)
            tables = flat

    lines: list[str] = []
    for t in tables[:30]:
        name = t.get("name") or "?"
        table_comment = str(t.get("comment") or "").strip()
        cols = t.get("columns", [])
        if isinstance(cols, list):
            rendered_cols: list[str] = []
            for c in cols[:8]:
                col_name = str(c.get("name") or "?")
                col_comment = str(c.get("comment") or "").strip()
                if col_comment:
                    rendered_cols.append(f"{col_name}[{col_comment[:18]}]")
                else:
                    rendered_cols.append(col_name)
            col_defs = ", ".join(rendered_cols)
            if len(cols) > 8:
                col_defs += f", ... (+{len(cols) - 8} more)"
            line = f"  {name}({col_defs})"
            if table_comment:
                line += f" -- {table_comment}"
            lines.append(line)
    result = "\n".join(lines)
    return result[:limit]


async def _load_skill_catalog(
    session: AsyncSession,
    datasource_id: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(SkillPack)
        .where(SkillPack.datasource_id == datasource_id)
        .where(SkillPack.status.notin_(["superseded", "rejected"]))
        .where(
            or_(
                SkillPack.origin != "runtime-learning",
                SkillPack.status != "draft",
            )
        )
        .order_by(SkillPack.confidence.desc(), SkillPack.name.asc(), SkillPack.id.asc())
        .limit(limit)
    )
    return [
        {
            "id": pack.id,
            "name": pack.name,
            "summary": pack.summary,
            "table_focus": pack.table_focus or [],
            "keywords": pack.keywords or [],
        }
        for pack in result.scalars().all()
    ]


def _format_skill_catalog(items: list[dict[str, Any]], limit: int = 1600) -> str:
    if not items:
        return ""
    lines = [
        "当前数据源可用技能目录（若命中用户问题，可直接调用 search_skill_documents 读取主文档）："
    ]
    for item in items:
        table_focus = item.get("table_focus") if isinstance(item.get("table_focus"), list) else []
        keywords = item.get("keywords") if isinstance(item.get("keywords"), list) else []
        details = []
        if table_focus:
            details.append("表: " + ", ".join(str(value) for value in table_focus[:6]))
        if keywords:
            details.append("关键词: " + ", ".join(str(value) for value in keywords[:8]))
        suffix = f"；{'；'.join(details)}" if details else ""
        lines.append(
            "- "
            f"id={item.get('id')} | name={item.get('name')} | "
            f"description={_truncate_text(item.get('summary') or '', 220)}"
            f"{suffix}"
        )
    return "\n".join(lines)[:limit]


class AgentResult(BaseModel):
    """Output from the autonomous agent."""
    response_text: str = Field(default="")
    generated_sql: str | None = None
    sql_explanation: str | None = None
    executed_results: list[dict] | None = None
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    tool_calls_made: list[str] = Field(default_factory=list)
    activated_skill_pack_names: list[str] = Field(default_factory=list)
    sql_execution_success: bool = False
    steps_used: int = 0


def _should_prefetch_retrieval(user_question: str) -> bool:
    """Skip prefetch for greetings and other non-analytical turns."""
    question = user_question.strip()
    if len(question) < 6:
        return False
    lowered = question.lower()
    small_talk_prefixes = (
        "你好",
        "您好",
        "hello",
        "hi",
        "谢谢",
        "感谢",
        "再见",
        "好的",
        "嗯",
        "ok",
    )
    if len(question) <= 16 and any(lowered.startswith(prefix) for prefix in small_talk_prefixes):
        return False
    return True


async def _prefetch_retrieval_references(
    *,
    user_question: str,
    tool_map: dict[str, Any],
    step_writer: Callable[[dict[str, Any]], None] | None,
) -> str:
    """Run QA/history retrieval before the LLM loop so demos always show the step."""
    sections: list[str] = []
    for tool_name in ("search_qa_examples", "search_history"):
        tool = tool_map.get(tool_name)
        if tool is None:
            continue
        args = {"query": user_question}
        if step_writer:
            step_writer(
                {
                    "step_id": "tool_call",
                    "phase": "start",
                    "tool": tool_name,
                    "step": 0,
                    "intent": _tool_intent_summary(tool_name, args),
                    "args_preview": _tool_args_preview(tool_name, args),
                    "prefetch": True,
                }
            )
        try:
            result = await tool.ainvoke(args)
        except Exception as exc:
            logger.warning("Prefetch tool %s failed: %s", tool_name, exc)
            result = json.dumps(
                {"error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                ensure_ascii=False,
            )
        if isinstance(result, str) and len(result) > 4000:
            result = result[:4000] + "\n... (预检索结果已截断)"
        summary = _summarize_tool_result(tool_name, result)
        if step_writer:
            step_writer(
                {
                    "step_id": "tool_call",
                    "phase": "error" if summary["is_error"] else "complete",
                    "tool": tool_name,
                    "step": 0,
                    "intent": _tool_intent_summary(tool_name, args),
                    "args_preview": _tool_args_preview(tool_name, args),
                    "summary": summary["summary"],
                    "result_preview": summary.get("preview"),
                    "prefetch": True,
                }
            )
        label = "QA 示例" if tool_name == "search_qa_examples" else "历史对话"
        sections.append(
            f"[{label}] {summary['summary']}"
            + (f"\n{summary['preview']}" if summary.get("preview") else "")
        )
    if not sections:
        return ""
    return "预检索参考（系统已在回答前自动检索，请优先参考并可在 trace 中核对）:\n" + "\n".join(sections)


def _truncate_text(value: Any, limit: int = 320) -> str:
    if isinstance(value, str):
        text = value.strip()
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _tool_intent_summary(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "introspect_schema":
        table_name = str(args.get("table_name") or "").strip()
        return f"检查表结构：{table_name}" if table_name else "检查可用表和字段"
    if tool_name == "execute_query":
        return "执行 SQL 获取真实结果"
    if tool_name == "search_skills":
        query = str(args.get("query") or "").strip()
        return f"搜索相关技能包：{query}" if query else "搜索可用技能包"
    if tool_name == "search_skill_documents":
        query = str(args.get("query") or "").strip()
        return f"读取技能文档并检索关键信息：{query}" if query else "读取技能文档"
    if tool_name == "search_qa_examples":
        query = str(args.get("query") or "").strip()
        return f"检索相关示例问答对：{query}" if query else "检索示例问答对"
    if tool_name == "recall_memory":
        return "检索历史记忆与已验证经验"
    if tool_name == "search_history":
        return "搜索历史对话与既往成功查询"
    if tool_name == "save_memory":
        title = str(args.get("title") or "").strip()
        return f"保存新记忆：{title}" if title else "保存新记忆"
    return f"调用工具：{tool_name}"


def _tool_args_preview(tool_name: str, args: dict[str, Any]) -> str | None:
    if tool_name == "execute_query":
        sql = str(args.get("sql") or "").strip()
        return _truncate_text(sql, 500) if sql else None
    if tool_name == "introspect_schema":
        table_name = str(args.get("table_name") or "").strip()
        return table_name or None
    if tool_name in {"search_skills", "search_qa_examples", "recall_memory", "search_history"}:
        query = str(args.get("query") or "").strip()
        return query or None
    if tool_name == "search_skill_documents":
        payload = {
            "skill_pack_id": args.get("skill_pack_id"),
            "query": args.get("query"),
            "limit": args.get("limit"),
        }
        return _truncate_text(payload, 320)
    if tool_name == "save_memory":
        payload = {
            "title": args.get("title"),
            "memory_type": args.get("memory_type"),
            "content_preview": _truncate_text(args.get("content") or "", 180),
        }
        return _truncate_text(payload, 320)
    return _truncate_text(args, 320) if args else None


def _summarize_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    payload = _safe_json_loads(result)
    if isinstance(payload, dict) and payload.get("error"):
        detail = payload.get("detail") or payload.get("reason") or payload.get("hint")
        return {
            "is_error": True,
            "summary": f"工具返回错误：{payload.get('error')}",
            "preview": _truncate_text(detail, 360) if detail else None,
        }

    if tool_name == "introspect_schema":
        if isinstance(payload, list):
            table_names = [
                str(item.get("table"))
                for item in payload
                if isinstance(item, dict) and item.get("table")
            ]
            return {
                "is_error": False,
                "summary": f"读取到 {len(table_names)} 张表",
                "preview": "、".join(table_names[:8]) if table_names else None,
            }
        if isinstance(payload, dict):
            table_name = str(payload.get("name") or payload.get("table") or "未知表")
            columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
            column_names = [
                str(item.get("name"))
                for item in columns
                if isinstance(item, dict) and item.get("name")
            ]
            return {
                "is_error": False,
                "summary": f"表 {table_name}，共 {len(column_names)} 个字段",
                "preview": "、".join(column_names[:10]) if column_names else None,
            }

    if tool_name == "execute_query" and isinstance(payload, dict):
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        total = int(payload.get("total_returned") or len(rows))
        truncated = bool(payload.get("truncated"))
        preview = _truncate_text(rows[0], 360) if rows else None
        return {
            "is_error": False,
            "summary": f"查询返回 {total} 行" + ("（已截断）" if truncated else ""),
            "preview": preview,
        }

    if tool_name == "search_skills" and isinstance(payload, dict):
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        names = [
            str(item.get("name"))
            for item in items
            if isinstance(item, dict) and item.get("name")
        ]
        return {
            "is_error": False,
            "summary": f"找到 {len(names)} 个候选技能包",
            "preview": "、".join(names[:8]) if names else payload.get("hint"),
        }

    if tool_name == "search_skill_documents" and isinstance(payload, dict):
        docs = payload.get("documents") if isinstance(payload.get("documents"), list) else []
        titles = [
            str(item.get("title"))
            for item in docs
            if isinstance(item, dict) and item.get("title")
        ]
        pack_name = str(payload.get("skill_pack") or "").strip()
        return {
            "is_error": False,
            "summary": f"{pack_name or '技能包'} 返回 {len(docs)} 份文档",
            "preview": "、".join(titles[:8]) if titles else None,
        }

    if tool_name == "search_qa_examples" and isinstance(payload, dict):
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        questions = [
            str(item.get("question"))
            for item in items
            if isinstance(item, dict) and item.get("question")
        ]
        return {
            "is_error": False,
            "summary": f"找到 {len(items)} 条相关示例问答对",
            "preview": "、".join(questions[:5]) if questions else payload.get("hint"),
        }

    if tool_name == "recall_memory" and isinstance(payload, dict):
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        titles = [
            str(item.get("title"))
            for item in items
            if isinstance(item, dict) and item.get("title")
        ]
        return {
            "is_error": False,
            "summary": f"召回 {len(items)} 条相关记忆",
            "preview": "、".join(titles[:8]) if titles else payload.get("hint"),
        }

    if tool_name == "search_history" and isinstance(payload, dict):
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        preview = None
        if items and isinstance(items[0], dict):
            first = items[0]
            preview = _truncate_text(
                {
                    "role": first.get("role"),
                    "content": first.get("content"),
                    "created_at": first.get("created_at"),
                },
                320,
            )
        return {
            "is_error": False,
            "summary": f"检索到 {len(items)} 条历史对话",
            "preview": preview or payload.get("hint"),
        }

    if tool_name == "save_memory" and isinstance(payload, dict):
        return {
            "is_error": False,
            "summary": f"记忆已保存：{payload.get('title') or payload.get('id') or 'draft'}",
            "preview": _truncate_text(payload, 280),
        }

    return {
        "is_error": False,
        "summary": "工具执行完成",
        "preview": _truncate_text(payload, 360) if payload else None,
    }


async def run_autonomous_agent(
    session: AsyncSession,
    *,
    datasource_id: str,
    user_question: str,
    thread_id: str | None = None,
    settings: Settings,
    memory_context: str = "",
    thread_summary: str = "",
    recent_turns: list[dict[str, str]] | None = None,
    step_writer: Callable[[dict[str, Any]], None] | None = None,
) -> AgentResult:
    """自主数据库 Agent 主入口：LLM + 工具循环，由模型自决调用哪些工具。

    由 LangGraph `run_agent_node` 调用；`step_writer` 非空时会把工具/推理摘要写入
    SSE `step` 事件，供 Workbench 时间线展示。

    执行阶段概览：
    1. 校验 LLM 配置
    2. 加载画像、schema 快照、技能目录等静态上下文
    3. 绑定 7 个闭包工具并构造首轮 messages
    4. （可选）对分析类问题预检索 QA / 历史
    5. 迭代：LLM → tool_calls → ToolMessage → 直至无工具或达步数上限
    6. 汇总 SQL、执行结果、激活技能名等写入 `AgentResult`（供图状态与学习审查）

    澄清（`needs_clarification`）不在此函数内触发，由上层 `run_agent_node` 根据
  返回值决定是否 `interrupt()`。
    """
    # --- 1. LLM 配置门禁 ---
    if not (
        settings.sql_agent_chat_api_key
        and settings.sql_agent_chat_base_url
        and settings.sql_agent_chat_model
    ):
        return AgentResult(
            response_text="LLM 未配置，无法提供服务。",
            needs_clarification=False,
        )

    # --- 2. 加载数据源侧静态上下文（不发起工具调用）---
    # profile / schema 来自 onboarding；skill_catalog 仅索引，正文需 search_skill_documents
    profile = await session.get(DatasourceProfile, datasource_id)
    schema_snapshot = await session.get(DatasourceSchemaSnapshot, datasource_id)
    schema_overview = _format_schema_overview(
        schema_snapshot.payload if schema_snapshot else None,
    )
    skill_catalog = await _load_skill_catalog(session, datasource_id)
    skill_catalog_context = _format_skill_catalog(skill_catalog)

    # --- 3. 构造工具集与可调用 LLM ---
    # tool_map 供循环内按名称派发；thread_id 传给 search_history 等同会话检索
    tools = build_agent_tools(session, settings, datasource_id, thread_id)
    tool_map = {t.name: t for t in tools}

    llm = ChatOpenAI(
        model=settings.sql_agent_chat_model,
        openai_api_key=settings.sql_agent_chat_api_key,
        openai_api_base=settings.sql_agent_chat_base_url,
        temperature=0,
        timeout=120,
        max_retries=1,
        extra_body={"enable_thinking": False},
    ).bind_tools(tools)

    # --- 4. 组装首轮 HumanMessage（压缩后的可迭代上下文）---
    # memory_context / thread_summary / recent_turns 由 prepare_runtime_node 预先准备好
    context_parts = [f"数据源 ID: {datasource_id}"]
    if profile and profile.summary:
        context_parts.append(f"数据源概述: {profile.summary}")
    if skill_catalog_context:
        context_parts.append(skill_catalog_context)
    if schema_overview:
        context_parts.append(f"表结构概览:\n{schema_overview}")
    if thread_summary:
        context_parts.append(f"对话摘要: {thread_summary}")
    recent_ctx = build_recent_turn_context(recent_turns or [])
    if recent_ctx:
        context_parts.append(f"近期对话:\n{recent_ctx}")
    if memory_context:
        context_parts.append(f"相关记忆:\n{memory_context}")

    # --- 5. 预检索 QA / 历史（分析类问题；结果写入 context，并产生 prefetch trace）---
    prefetch_context = ""
    if _should_prefetch_retrieval(user_question):
        prefetch_context = await _prefetch_retrieval_references(
            user_question=user_question,
            tool_map=tool_map,
            step_writer=step_writer,
        )
        if prefetch_context:
            context_parts.append(prefetch_context)

    # SystemMessage 在循环内会按轮刷新时间基准；HumanMessage 仅首轮注入上下文
    messages: list[Any] = [
        SystemMessage(content=_build_system_message(settings)),
        HumanMessage(
            content=f"{''.join(chr(10) + chr(10) + p for p in context_parts)}\n\n用户问题: {user_question}"
        ),
    ]

    # --- 6. 跨轮累积状态（写入 AgentResult → WorkflowState → 学习审查 / 持久化）---
    tool_calls_made: list[str] = []
    activated_skill_pack_names: list[str] = []
    activated_skill_pack_name_set: set[str] = set()  # 去重，避免 search_* 重复追加
    last_sql: str | None = None
    last_sql_explanation: str | None = None
    last_executed_results: list[dict] | None = None
    sql_execution_success = False  # 仅 execute_query 成功且无 error 时为 True
    max_steps = int(getattr(settings, "sql_agent_autonomous_max_steps", DEFAULT_MAX_AGENT_STEPS))
    unlimited_steps = max_steps <= 0  # <=0 表示不限制迭代（调试用）
    budget_warning_threshold = max(
        1,
        min(DEFAULT_BUDGET_WARNING_THRESHOLD, max_steps - 3),
    ) if not unlimited_steps else None

    if step_writer:
        step_writer({
            "step_id": "agent_loop",
            "phase": "start",
            "max_steps": None if unlimited_steps else max_steps,
            "unlimited": unlimited_steps,
            "skill_catalog_count": len(skill_catalog),
        })

    # --- 7. 工具循环：每轮一次 LLM 调用，可并行多个 tool_call ---
    step = 0
    while unlimited_steps or step < max_steps:
        if (
            step_writer
            and not unlimited_steps
            and budget_warning_threshold is not None
            and step == budget_warning_threshold
        ):
            step_writer({"step_id": "budget_warning", "phase": "warning", "remaining": max_steps - step})

        try:
            # 每轮刷新系统消息中的「当前参考时间」，长循环里「今天/近 N 天」仍可对齐
            messages[0] = SystemMessage(content=_build_system_message(settings))
            with trace_observation(
                "generate-agent-step",
                as_type="generation",
                input={"message_count": len(messages), "step": step + 1},
                input_summary={"message_count": len(messages), "step": step + 1},
                metadata={"datasource_id": datasource_id, "thread_id": thread_id},
                model=settings.sql_agent_chat_model,
            ) as generation:
                ai_message: AIMessage = await llm.ainvoke(messages)
                if generation is not None:
                    response_text = content_to_text(ai_message.content)
                    generation.update(
                        output=trace_content(
                            response_text,
                            fallback={
                                "response_chars": len(response_text),
                                "tool_call_count": len(getattr(ai_message, "tool_calls", None) or []),
                            },
                        ),
                        usage_details=usage_details_from_message(ai_message),
                    )
        except Exception as exc:
            logger.error("Agent LLM call failed at step %d: %s", step, exc)
            return AgentResult(
                response_text=f"LLM 调用失败: {type(exc).__name__}",
                steps_used=step,
                tool_calls_made=tool_calls_made,
                activated_skill_pack_names=activated_skill_pack_names,
                sql_execution_success=sql_execution_success,
            )

        messages.append(ai_message)
        ai_tool_calls = getattr(ai_message, "tool_calls", None) or []
        assistant_note = content_to_text(ai_message.content).strip()

        # 7a. 无工具调用 → Agent 认为可以作答，结束循环
        if not ai_tool_calls:
            response = content_to_text(ai_message.content)

            # 若本轮未通过 execute_query 留下 SQL，尝试从 Markdown 代码块回填
            sql_match = _extract_sql_from_response(response)
            if sql_match and not last_sql:
                last_sql = sql_match

            if step_writer:
                if response.strip():
                    step_writer(
                        {
                            "step_id": "assistant_message",
                            "phase": "complete",
                            "content": response,
                            "has_sql": bool(last_sql),
                        }
                    )
                step_writer({
                    "step_id": "agent_loop",
                    "phase": "complete",
                    "steps_used": step + 1,
                    "tool_calls": tool_calls_made,
                    "has_sql": bool(last_sql),
                })

            return AgentResult(
                response_text=response,
                generated_sql=last_sql,
                sql_explanation=last_sql_explanation,
                executed_results=last_executed_results,
                tool_calls_made=tool_calls_made,
                activated_skill_pack_names=activated_skill_pack_names,
                sql_execution_success=sql_execution_success,
                steps_used=step + 1,
            )

        # 7b. 有工具前：把模型给出的简短中文进度说明写入 trace（非私有 CoT）
        if assistant_note and step_writer:
            step_writer(
                {
                    "step_id": "reasoning_note",
                    "phase": "note",
                    "step": step + 1,
                    "text": _truncate_text(assistant_note, 1200),
                }
            )

        # 7c. 逐个执行 tool_call，结果以 ToolMessage 追加回 messages 供下一轮 LLM 阅读
        for tc in ai_tool_calls:
            tool_name = tc["name"]
            tool_calls_made.append(tool_name)
            tool_args = tc["args"] if isinstance(tc.get("args"), dict) else {}
            args_preview = _tool_args_preview(tool_name, tool_args)

            if step_writer:
                step_writer({
                    "step_id": "tool_call",
                    "phase": "start",
                    "tool": tool_name,
                    "step": step + 1,
                    "intent": _tool_intent_summary(tool_name, tool_args),
                    "args_preview": args_preview,
                })

            if tool_name not in tool_map:
                messages.append(ToolMessage(
                    content=json.dumps({"error": f"unknown_tool: {tool_name}"}),
                    tool_call_id=tc["id"],
                ))
                continue

            try:
                with trace_observation(
                    f"call-{tool_name.replace('_', '-')}",
                    as_type="retriever" if tool_name in _RETRIEVER_TOOL_NAMES else "tool",
                    input=tool_args,
                    input_summary={"argument_names": sorted(tool_args)},
                    metadata={
                        "datasource_id": datasource_id,
                        "thread_id": thread_id,
                        "step": step + 1,
                    },
                ) as tool_span:
                    result = await tool_map[tool_name].ainvoke(tc["args"])
                    if tool_span is not None:
                        tool_span.update(
                            output=trace_content(
                                result,
                                fallback={"result_chars": len(str(result))},
                            )
                        )
            except Exception as exc:
                # 工具层约定：错误进 JSON 字符串，不抛到图外，便于模型自我修正
                logger.warning("Tool %s failed: %s", tool_name, exc)
                result = json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:200]}"})

            # 防止大结果撑爆上下文（schema / 宽表查询）
            if isinstance(result, str) and len(result) > 8000:
                truncated = result[:8000] + "\n... (结果已截断，共 {} 字符)".format(len(result))
                result = truncated

            # 学习信号：成功执行且无 error 时标记，供 post-turn learning 沉淀 QA
            if tool_name == "execute_query":
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and not parsed.get("error") and "rows" in parsed:
                        last_executed_results = parsed["rows"]
                        sql_execution_success = True
                        sql_arg = tc["args"].get("sql", "")
                        if sql_arg:
                            last_sql = sql_arg
                except (json.JSONDecodeError, TypeError):
                    pass

            # 记录本轮命中的技能包名（学习审查与 Admin 可观测性）
            if tool_name == "search_skills":
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict):
                        items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
                        for item in items[:5]:
                            if not isinstance(item, dict):
                                continue
                            pack_name = str(item.get("name") or "").strip()
                            if pack_name and pack_name not in activated_skill_pack_name_set:
                                activated_skill_pack_name_set.add(pack_name)
                                activated_skill_pack_names.append(pack_name)
                except (json.JSONDecodeError, TypeError):
                    pass

            if tool_name == "search_skill_documents":
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict):
                        pack_name = str(parsed.get("skill_pack") or "").strip()
                        if pack_name and pack_name not in activated_skill_pack_name_set:
                            activated_skill_pack_name_set.add(pack_name)
                            activated_skill_pack_names.append(pack_name)
                except (json.JSONDecodeError, TypeError):
                    pass

            messages.append(ToolMessage(
                content=result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str),
                tool_call_id=tc["id"],
            ))

            if step_writer:
                result_summary = _summarize_tool_result(tool_name, result)
                step_writer({
                    "step_id": "tool_call",
                    "phase": "error" if result_summary["is_error"] else "complete",
                    "tool": tool_name,
                    "step": step + 1,
                    "intent": _tool_intent_summary(tool_name, tool_args),
                    "args_preview": args_preview,
                    "summary": result_summary["summary"],
                    "result_preview": result_summary.get("preview"),
                })

        step += 1

    # --- 8. 步数耗尽：仍返回已收集的 SQL/结果，避免完全空响应 ---
    logger.warning("Agent hit max steps (%d) for question: %s", max_steps, user_question[:100])
    if step_writer:
        step_writer({"step_id": "agent_loop", "phase": "budget_exhausted", "steps_used": max_steps})

    return AgentResult(
        response_text="我已经进行了多轮分析，以下是目前的结果。",
        generated_sql=last_sql,
        sql_explanation=last_sql_explanation,
        executed_results=last_executed_results,
        tool_calls_made=tool_calls_made,
        activated_skill_pack_names=activated_skill_pack_names,
        sql_execution_success=sql_execution_success,
        steps_used=max_steps,
    )


def _extract_sql_from_response(text: str) -> str | None:
    """Extract SQL from markdown code blocks in the response."""
    import re
    patterns = [
        re.compile(r"```sql\s*\n(.*?)```", re.DOTALL | re.IGNORECASE),
        re.compile(r"```\s*\n(SELECT\s.*?)```", re.DOTALL | re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            sql = match.group(1).strip()
            if sql:
                return sql
    if text.strip().upper().startswith("SELECT ") and "```" not in text:
        return text.strip()
    return None
