"""Datasource onboarding analysis and candidate skill-pack generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import anyio
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db_url import normalize_database_driver_url
from app.core.llm_structured import content_to_text, parse_model_output
from app.db.models.datasource import Datasource
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.skill_document import SkillDocument
from app.db.models.skill_pack import SkillPack
from app.rag.embed_service import build_embedding_client
from app.services.datasource_introspection import (
    PROFILE_QUERY_ROW_LIMIT,
    build_onboarding_profile_payload,
    introspect_schema_payload,
    sanitize_error_message,
)
from app.services.runtime_rules import merge_profile_runtime_rules
from app.services.skill_documents import upsert_canonical_skill_document
from app.sql.safety import SqlSafetyService

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_ONBOARDING_SYSTEM_PROMPT = """
你是一个企业级 Text-to-SQL 系统的数据源 Onboarding 分析代理。

你的职责是对一个新数据源进行深度分析，推断其业务子领域，并起草候选技能包（Skill Pack），
这些技能包将在用户提问时被自动激活以辅助 SQL 生成。

规则：
- 保守原则：宁缺毋滥，优先生成少量精准的技能包，而非大量重叠的包。
- 利用表结构、字段类型和采样数据来推断业务实体、指标和工作流概念。
- 每个候选技能包必须围绕一个连贯的业务能力领域。
- 将无法确定的业务假设作为待确认问题明确列出。
- 所有文案必须使用中文。
- 仅返回符合要求 schema 的合法 JSON，不要包含 markdown 或其他注释文字。
"""


class OnboardingQuestion(BaseModel):
    question: str = Field(..., min_length=1)
    reason: str = Field(default="")
    priority: int = Field(default=1, ge=1, le=5)
    input_kind: str = Field(default="text")
    options: list[str] = Field(default_factory=list)

    @classmethod
    def _normalize_input_kind(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip() in {"text", "single_select", "multi_select"}:
            return value.strip()
        return "text"

    @model_validator(mode="before")
    @classmethod
    def normalize_question(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"question": value.strip()}
        if isinstance(value, dict):
            payload = dict(value)
            payload["question"] = str(payload.get("question") or "").strip()
            payload["reason"] = str(payload.get("reason") or "")
            payload["input_kind"] = cls._normalize_input_kind(payload.get("input_kind"))
            raw_options = payload.get("options")
            payload["options"] = (
                [str(item).strip() for item in raw_options if str(item).strip()]
                if isinstance(raw_options, list)
                else []
            )
            return payload
        return value


class SkillDocumentDraft(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    document_type: str = Field(default="analysis-note")
    weight: float = Field(default=1.0, ge=0.1, le=3.0)

    @model_validator(mode="before")
    @classmethod
    def normalize_document(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            return {
                "title": text[:80] or "分析文档",
                "content": text or "暂无内容",
            }
        return value


class SkillPackDraft(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(..., min_length=1)
    business_overview: str = Field(default="")
    schema_notes: str = Field(default="")
    keywords: list[str] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    table_focus: list[str] = Field(default_factory=list)
    business_rules: list[dict[str, Any]] = Field(default_factory=list)
    seed_documents: list[SkillDocumentDraft] = Field(default_factory=list)
    open_questions: list[OnboardingQuestion] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @staticmethod
    def _normalize_kv_list(
        value: Any,
        *,
        key_name: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str) and item.strip():
                normalized.append({key_name: item.strip()})
        return normalized

    @model_validator(mode="before")
    @classmethod
    def normalize_pack(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            return {
                "name": text[:80] or "未命名技能",
                "slug": _slugify(text[:80] or "skill-pack"),
                "summary": text or "暂无摘要",
            }
        if isinstance(value, dict):
            payload = dict(value)
            name = str(payload.get("name") or payload.get("title") or "未命名技能").strip()
            payload["name"] = name
            payload["slug"] = str(payload.get("slug") or _slugify(name)).strip()
            summary = payload.get("summary")
            if isinstance(summary, dict):
                summary = summary.get("summary") or summary.get("description") or summary.get("name")
            payload["summary"] = str(summary or name or "暂无摘要").strip()
            payload["business_overview"] = str(payload.get("business_overview") or "")
            payload["schema_notes"] = str(payload.get("schema_notes") or "")
            payload["keywords"] = [
                str(item).strip()
                for item in (payload.get("keywords") or [])
                if str(item).strip()
            ] if isinstance(payload.get("keywords"), list) else []
            payload["metrics"] = cls._normalize_kv_list(payload.get("metrics"), key_name="name")
            payload["entities"] = cls._normalize_kv_list(payload.get("entities"), key_name="name")
            payload["business_rules"] = cls._normalize_kv_list(payload.get("business_rules"), key_name="rule")
            payload["table_focus"] = [
                str(item).strip()
                for item in (payload.get("table_focus") or [])
                if str(item).strip()
            ] if isinstance(payload.get("table_focus"), list) else []
            return payload
        return value


class OnboardingAnalysisOutput(BaseModel):
    datasource_summary: str = Field(..., min_length=1)
    business_overview: str = Field(default="")
    candidate_skill_packs: list[SkillPackDraft] = Field(default_factory=list)
    unresolved_questions: list[OnboardingQuestion] = Field(default_factory=list)
    profile_highlights: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_output(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        summary = payload.get("datasource_summary")
        if isinstance(summary, dict):
            summary = (
                summary.get("summary")
                or summary.get("description")
                or summary.get("name")
                or json.dumps(summary, ensure_ascii=False)
            )
        payload["datasource_summary"] = str(summary or "").strip()
        if not payload["datasource_summary"]:
            pack_like = payload.get("candidate_skill_packs")
            if isinstance(pack_like, list) and pack_like and isinstance(pack_like[0], dict):
                payload["datasource_summary"] = str(
                    pack_like[0].get("summary")
                    or pack_like[0].get("name")
                    or "已完成数据源分析。"
                )
            else:
                payload["datasource_summary"] = "已完成数据源分析。"
        payload["business_overview"] = str(payload.get("business_overview") or "")
        raw_packs = payload.get("candidate_skill_packs")
        if isinstance(raw_packs, dict):
            payload["candidate_skill_packs"] = [raw_packs]
        elif not isinstance(raw_packs, list):
            payload["candidate_skill_packs"] = []
        raw_questions = payload.get("unresolved_questions")
        if isinstance(raw_questions, dict):
            payload["unresolved_questions"] = [raw_questions]
        elif not isinstance(raw_questions, list):
            payload["unresolved_questions"] = []
        if not isinstance(payload.get("profile_highlights"), dict):
            payload["profile_highlights"] = {}
        return payload


class OnboardingPreviewItem(BaseModel):
    name: str
    domain_label: str
    summary: str
    confidence: float
    status: str


class OnboardingRunResult(BaseModel):
    datasource_id: str
    analysis_status: str
    summary: str
    skill_pack_count: int
    unresolved_question_count: int
    domain_count: int = 0
    preview_items: list[OnboardingPreviewItem] = Field(default_factory=list)
    profile_json: dict[str, Any] | None = None


def _slugify(value: str) -> str:
    slug = _NON_ALNUM_RE.sub("-", value.lower()).strip("-")
    return slug or "skill-pack"


def _normalize_slug(name: str, proposed_slug: str) -> str:
    base = _slugify(proposed_slug or name)
    return base[:255]


def _truncate(value: str, limit: int = 240) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _preview_json(value: Any, limit: int = 320) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        rendered = str(value)
    return _truncate(rendered, limit)


def _tool_args_preview(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "describe_table":
        return str(args.get("table_name") or "")
    if tool_name == "run_profile_query":
        sql = str(args.get("sql") or "").strip()
        return _truncate(sql, 240)
    return _preview_json(args, 240)


def _tool_result_preview(tool_name: str, result: Any) -> tuple[str, dict[str, Any] | None]:
    if tool_name == "list_tables" and isinstance(result, list):
        preview = "、".join(str(item) for item in result[:8])
        return (
            f"发现 {len(result)} 张表" + (f"：{preview}" if preview else ""),
            {"table_count": len(result), "tables": [str(item) for item in result[:12]]},
        )
    if tool_name == "read_schema_snapshot" and isinstance(result, dict):
        tables = result.get("tables")
        table_names = [
            str(item.get("name"))
            for item in tables
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ] if isinstance(tables, list) else []
        return (
            f"读取结构快照，包含 {len(table_names)} 张表",
            {"table_count": len(table_names), "tables": table_names[:12]},
        )
    if tool_name == "describe_table" and isinstance(result, dict):
        table_name = str(result.get("name") or "")
        columns = result.get("columns")
        column_names = [
            str(item.get("name"))
            for item in columns
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ] if isinstance(columns, list) else []
        return (
            f"{table_name} 含 {len(column_names)} 个字段",
            {"table": table_name, "columns": column_names[:16]},
        )
    if tool_name == "run_profile_query" and isinstance(result, dict):
        rows = result.get("rows")
        row_count = int(result.get("row_count") or (len(rows) if isinstance(rows, list) else 0))
        first_row = rows[0] if isinstance(rows, list) and rows else None
        return (
            f"查询返回 {row_count} 行",
            {
                "sql": str(result.get("sql") or ""),
                "row_count": row_count,
                "first_row": first_row,
            },
        )
    return (_preview_json(result, 240), None)


def _safe_query_sql(sql: str) -> str:
    candidate = (sql or "").strip().rstrip(";")
    ok, reason = SqlSafetyService.validate(candidate)
    if not ok:
        raise ValueError(reason)
    return (
        "SELECT * FROM ("
        f"{candidate}"
        f") AS onboarding_profile_query LIMIT {PROFILE_QUERY_ROW_LIMIT}"
    )


@dataclass(slots=True)
class _OnboardingInspector:
    connection_url: str
    dialect: str
    schema_payload: dict[str, Any]

    def list_tables(self) -> list[str]:
        return [str(table.get("name")) for table in self.schema_payload.get("tables", [])]

    def read_schema_snapshot(self) -> dict[str, Any]:
        return self.schema_payload

    def describe_table(self, table_name: str) -> dict[str, Any]:
        for table in self.schema_payload.get("tables", []):
            if str(table.get("name")) == table_name:
                return table
        raise ValueError(f"unknown_table:{table_name}")

    def run_profile_query(self, sql: str) -> dict[str, Any]:
        safe_sql = _safe_query_sql(sql)
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        engine = create_engine(normalize_database_driver_url(self.connection_url), poolclass=NullPool)
        with engine.connect() as conn:
            rows = conn.execute(text(safe_sql)).mappings()
            materialized = [
                {str(key): _json_safe(value) for key, value in row.items()}
                for row in rows
            ]
        return {
            "sql": safe_sql,
            "row_count": len(materialized),
            "rows": materialized,
        }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _build_onboarding_tools(inspector: _OnboardingInspector):
    @tool
    def list_tables() -> list[str]:
        """List tables visible in the datasource."""

        return inspector.list_tables()

    @tool
    def read_schema_snapshot() -> dict[str, Any]:
        """Return the precomputed schema-and-samples snapshot for the datasource."""

        return inspector.read_schema_snapshot()

    @tool
    def describe_table(table_name: str) -> dict[str, Any]:
        """Return columns, keys, and sampled rows for one table."""

        return inspector.describe_table(table_name)

    @tool
    def run_profile_query(sql: str) -> dict[str, Any]:
        """Run a bounded read-only SQL query for profiling. SELECT only."""

        return inspector.run_profile_query(sql)

    return [list_tables, read_schema_snapshot, describe_table, run_profile_query]


_MAX_LLM_ONBOARDING_ATTEMPTS = 2

OnboardingProgressReporter = Callable[[str, str, dict[str, Any] | None], Awaitable[None]]


async def _emit_onboarding_progress(
    reporter: OnboardingProgressReporter | None,
    phase: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if reporter is None:
        return
    await reporter(phase, message, payload)


async def _llm_onboarding_single_attempt(
    datasource: Datasource,
    schema_payload: dict[str, Any],
    settings: Settings,
    *,
    attempt: int,
    user_context: dict[str, Any] | None = None,
    progress_callback: OnboardingProgressReporter | None = None,
) -> OnboardingAnalysisOutput:
    inspector = _OnboardingInspector(
        connection_url=datasource.connection_url,
        dialect=datasource.dialect,
        schema_payload=schema_payload,
    )
    tools = _build_onboarding_tools(inspector)
    tool_map = {item.name: item for item in tools}
    llm = ChatOpenAI(
        model=settings.sql_agent_chat_model,
        openai_api_key=settings.sql_agent_chat_api_key,
        openai_api_base=settings.sql_agent_chat_base_url,
        temperature=0,
        timeout=180,
        max_retries=1,
        extra_body={"enable_thinking": False},
    ).bind_tools(tools)
    messages: list[Any] = [
        SystemMessage(content=_ONBOARDING_SYSTEM_PROMPT.strip()),
        HumanMessage(
            content=(
                "请分析以下数据源，并生成包含以下字段的 JSON：\n"
                "datasource_summary, business_overview, candidate_skill_packs, "
                "unresolved_questions, profile_highlights。\n"
                "每个技能包（skill pack）必须包含：name, slug, summary, business_overview, "
                "candidate_skill_packs 中只保留知识型内容：name, slug, summary, business_overview, schema_notes, keywords, metrics, entities, table_focus, business_rules, seed_documents, open_questions, confidence。\n"
                "不要为技能包初始化示例问答对；问答案例后续由运行时单独沉淀到独立 QA 检索层。\n"

                "input_kind（text 或 single_select）与 options（候选选项数组，可为空）。\n\n"
                f"数据源 ID：{datasource.id}\n"
                f"显示名称：{datasource.display_name}\n"
                f"数据库方言：{datasource.dialect}\n"
                f"Schema 快照摘要：{json.dumps(schema_payload, ensure_ascii=False)[:12000]}\n"
                f"用户补充信息：{json.dumps(user_context or {}, ensure_ascii=False)[:4000]}"
            )
        ),
    ]

    for _ in range(10):
        ai_message = await llm.ainvoke(messages)
        messages.append(ai_message)
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        assistant_note = content_to_text(ai_message.content).strip()
        if assistant_note and tool_calls:
            await _emit_onboarding_progress(
                progress_callback,
                "llm_reasoning",
                "分析代理给出了本轮计划。",
                {
                    "attempt": attempt,
                    "text": _truncate(assistant_note, 1200),
                },
            )
        if not tool_calls:
            await _emit_onboarding_progress(
                progress_callback,
                "llm_parse",
                "正在整理技能包与画像结果。",
                {"attempt": attempt},
            )
            try:
                return parse_model_output(
                    OnboardingAnalysisOutput,
                    content_to_text(ai_message.content),
                )
            except ValidationError as exc:
                messages.append(
                    HumanMessage(
                        content=(
                            "请仅返回符合 schema 的合法 JSON，不要包含 markdown 或其他文字。"
                            f" 上一次输出的结构问题摘要：{str(exc)[:1000]}"
                        )
                    )
                )
                ai_message = await llm.ainvoke(messages)
                return parse_model_output(
                    OnboardingAnalysisOutput,
                    content_to_text(ai_message.content),
                )
        for tool_call in tool_calls:
            tool_obj = tool_map[tool_call["name"]]
            tool_args = tool_call["args"] if isinstance(tool_call.get("args"), dict) else {}
            args_preview = _tool_args_preview(tool_call["name"], tool_args)
            await _emit_onboarding_progress(
                progress_callback,
                "llm_tool_call",
                f"分析代理正在调用 {tool_call['name']}。",
                {
                    "attempt": attempt,
                    "tool": tool_call["name"],
                    "args": tool_args,
                    "args_preview": args_preview,
                },
            )
            result = await anyio.to_thread.run_sync(tool_obj.invoke, tool_args)
            result_preview, result_payload = _tool_result_preview(tool_call["name"], result)
            await _emit_onboarding_progress(
                progress_callback,
                "llm_tool_result",
                f"{tool_call['name']} 已返回结果。",
                {
                    "attempt": attempt,
                    "tool": tool_call["name"],
                    "preview": result_preview,
                    "result": result_payload,
                },
            )
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=tool_call["id"],
                )
            )
    raise RuntimeError("onboarding_agent_max_steps")


async def llm_onboarding_analysis(
    datasource: Datasource,
    schema_payload: dict[str, Any],
    settings: Settings,
    *,
    user_context: dict[str, Any] | None = None,
    progress_callback: OnboardingProgressReporter | None = None,
) -> OnboardingAnalysisOutput:
    if not (
        settings.sql_agent_chat_api_key
        and settings.sql_agent_chat_base_url
        and settings.sql_agent_chat_model
    ):
        raise RuntimeError("chat_disabled")

    last_error: Exception | None = None
    for attempt in range(_MAX_LLM_ONBOARDING_ATTEMPTS):
        try:
            await _emit_onboarding_progress(
                progress_callback,
                "llm_attempt",
                f"开始第 {attempt + 1} 轮智能分析。",
                {"attempt": attempt + 1, "max_attempts": _MAX_LLM_ONBOARDING_ATTEMPTS},
            )
            return await _llm_onboarding_single_attempt(
                datasource,
                schema_payload,
                settings,
                attempt=attempt + 1,
                user_context=user_context,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            last_error = exc
            await _emit_onboarding_progress(
                progress_callback,
                "llm_attempt_failed",
                f"第 {attempt + 1} 轮分析失败，准备重试。",
                {
                    "attempt": attempt + 1,
                    "error": sanitize_error_message(exc),
                },
            )
            if attempt < _MAX_LLM_ONBOARDING_ATTEMPTS - 1:
                import logging
                logging.getLogger(__name__).warning(
                    "onboarding LLM attempt %d failed, retrying: %s", attempt + 1, exc
                )
    raise last_error  # type: ignore[misc]


async def _embed_skill_artifacts(
    *,
    settings: Settings,
    skill_pack: SkillPack,
    documents: list[SkillDocument],
    progress_callback: OnboardingProgressReporter | None = None,
) -> None:
    client = build_embedding_client(settings)
    now = datetime.now(timezone.utc)
    skill_pack.embedding_updated_at = now
    skill_pack.embedding_error = None
    if client is None:
        skill_pack.summary_embedding = None
        skill_pack.embedding_status = "pending"
        skill_pack.embedding_error = "Embedding configuration is required."
        for document in documents:
            document.embedding = None
            document.embedding_status = "pending"
            document.embedding_error = "Embedding configuration is required."
            document.embedding_updated_at = now
        return

    try:
        await _emit_onboarding_progress(
            progress_callback,
            "embedding_pack",
            f"正在生成技能包「{skill_pack.name}」的向量表示。",
            {"skill_pack_id": skill_pack.id, "document_count": len(documents)},
        )
        skill_pack.summary_embedding = await client.aembed_query(
            f"{skill_pack.name}\n{skill_pack.summary}\n{skill_pack.business_overview or ''}"
        )
        skill_pack.embedding_status = "ready"
        skill_pack.embedding_error = None
    except Exception as exc:
        skill_pack.summary_embedding = None
        skill_pack.embedding_status = "failed"
        skill_pack.embedding_error = sanitize_error_message(exc)

    for document in documents:
        document.embedding_updated_at = now
        document.embedding_error = None
        try:
            await _emit_onboarding_progress(
                progress_callback,
                "embedding_document",
                f"正在生成文档「{document.title}」的向量表示。",
                {"skill_pack_id": skill_pack.id, "document_id": document.id},
            )
            document.embedding = await client.aembed_query(document.content)
            document.embedding_status = "ready"
            document.embedding_error = None
        except Exception as exc:
            document.embedding = None
            document.embedding_status = "failed"
            document.embedding_error = sanitize_error_message(exc)


async def _upsert_candidate_skill_packs(
    session: AsyncSession,
    datasource: Datasource,
    analysis: OnboardingAnalysisOutput,
    settings: Settings,
    *,
    progress_callback: OnboardingProgressReporter | None = None,
) -> list[SkillPack]:
    existing_rows = await session.execute(
        select(SkillPack).where(
            SkillPack.datasource_id == datasource.id,
            SkillPack.origin == "onboarding",
        )
    )
    existing = {row.slug: row for row in existing_rows.scalars().all()}
    active_slugs: set[str] = set()
    persisted: list[SkillPack] = []

    for draft in analysis.candidate_skill_packs:
        slug = _normalize_slug(draft.name, draft.slug)
        await _emit_onboarding_progress(
            progress_callback,
            "persist_skill_pack",
            f"正在写入技能包「{draft.name}」。",
            {"slug": slug},
        )
        active_slugs.add(slug)
        row = existing.get(slug)
        if row is None:
            row = SkillPack(
                datasource_id=datasource.id,
                name=draft.name.strip(),
                slug=slug,
                origin="onboarding",
            )
            session.add(row)
            await session.flush()
            existing[slug] = row

        row.name = draft.name.strip()
        row.summary = _truncate(draft.summary, 800)
        row.business_overview = _truncate(draft.business_overview, 4000)
        row.schema_notes = _truncate(draft.schema_notes, 4000)
        row.status = "ready"
        row.activation_mode = "auto"
        row.confidence = float(draft.confidence)
        row.keywords = [str(item).strip() for item in draft.keywords if str(item).strip()][:24]
        row.metrics = draft.metrics[:24]
        row.entities = draft.entities[:24]
        row.table_focus = [str(item).strip() for item in draft.table_focus if str(item).strip()][:16]
        row.business_rules = draft.business_rules[:24]
        row.example_sql_pairs = []
        row.example_questions = []
        row.pack_metadata = {
            "generated_by": analysis.profile_highlights.get("mode", "llm"),
            "agent_followups": [question.model_dump() for question in draft.open_questions],
            "datasource_summary": analysis.datasource_summary,
        }

        await session.execute(
            delete(SkillDocument).where(SkillDocument.skill_pack_id == row.id)
        )
        supplemental_documents = [
            {
                "title": document.title.strip(),
                "content": document.content.strip(),
            }
            for document in draft.seed_documents
            if document.title.strip() and document.content.strip()
        ]
        canonical_document = await upsert_canonical_skill_document(
            session,
            row,
            supplemental_documents=supplemental_documents,
            source="onboarding-agent",
        )
        persisted_documents = [canonical_document]
        await _embed_skill_artifacts(
            settings=settings,
            skill_pack=row,
            documents=persisted_documents,
            progress_callback=progress_callback,
        )
        persisted.append(row)

    for slug, row in existing.items():
        if slug not in active_slugs:
            row.status = "superseded"
            row.activation_mode = "manual"

    await session.flush()
    return persisted


def _build_run_preview_items(skill_packs: list[SkillPack]) -> list[OnboardingPreviewItem]:
    preview_items: list[OnboardingPreviewItem] = []
    for pack in skill_packs:
        preview_items.append(
            OnboardingPreviewItem(
                name=pack.name,
                domain_label=pack.name,
                summary=_truncate(pack.summary, 240),
                confidence=float(pack.confidence or 0.0),
                status=pack.status,
            )
        )
    return preview_items


async def run_onboarding_for_datasource(
    session: AsyncSession,
    datasource_id: str,
    settings: Settings,
    progress_callback: OnboardingProgressReporter | None = None,
) -> OnboardingRunResult:
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise ValueError("datasource_not_found")

    profile = await session.get(DatasourceProfile, datasource_id)
    if profile is None:
        profile = DatasourceProfile(datasource_id=datasource_id)
        session.add(profile)

    profile.analysis_status = "running"
    profile.analysis_error = None
    await session.flush()
    await _emit_onboarding_progress(
        progress_callback,
        "prepare_schema_snapshot",
        "正在重新采集结构快照。",
        {"datasource_id": datasource_id},
    )

    try:
        snapshot_payload = await anyio.to_thread.run_sync(
            introspect_schema_payload,
            datasource.connection_url,
            datasource.dialect,
        )
        rich_profile_payload = await anyio.to_thread.run_sync(
            build_onboarding_profile_payload,
            datasource.connection_url,
            datasource.dialect,
        )
        await _emit_onboarding_progress(
            progress_callback,
            "build_rich_profile",
            "结构采集完成，正在构建分析画像。",
            {
                "table_count": int(rich_profile_payload.get("table_count", 0)),
                "column_count": int(rich_profile_payload.get("column_count", 0)),
            },
        )
    except Exception as exc:
        profile.analysis_status = "failed"
        profile.analysis_error = sanitize_error_message(exc)
        await session.commit()
        raise ValueError("datasource_onboarding_failed") from exc

    snapshot = await session.get(DatasourceSchemaSnapshot, datasource_id)
    captured_at = datetime.now(timezone.utc)
    if snapshot is None:
        snapshot = DatasourceSchemaSnapshot(
            datasource_id=datasource_id,
            payload=snapshot_payload,
            captured_at=captured_at,
        )
        session.add(snapshot)
    else:
        snapshot.payload = snapshot_payload
        snapshot.captured_at = captured_at

    table_count = int(rich_profile_payload.get("table_count", 0))
    column_count = int(rich_profile_payload.get("column_count", 0))
    existing_context = {}
    if isinstance(profile.profile_json, dict):
        raw_context = profile.profile_json.get("onboarding_context")
        if isinstance(raw_context, dict):
            existing_context = raw_context

    try:
        await _emit_onboarding_progress(
            progress_callback,
            "llm_analysis",
            "正在调用模型分析数据源并生成候选技能包。",
            {
                "table_count": table_count,
                "column_count": column_count,
                "has_user_context": bool(existing_context),
            },
        )
        analysis = await llm_onboarding_analysis(
            datasource,
            rich_profile_payload,
            settings,
            user_context=existing_context,
            progress_callback=progress_callback,
        )
        mode = "llm"
    except Exception as exc:
        mode = "failed"
        analysis = OnboardingAnalysisOutput(
            datasource_summary=(
                f"数据源 {datasource.display_name} 包含 {table_count} 张表、"
                f"{column_count} 个字段。LLM 分析未能完成，未生成技能包。"
            ),
            business_overview="",
            candidate_skill_packs=[],
            unresolved_questions=[],
            profile_highlights={
                "mode": "failed",
                "table_count": table_count,
                "column_count": column_count,
                "llm_error": sanitize_error_message(exc),
            },
        )

    analysis.profile_highlights.setdefault("mode", mode)
    await _emit_onboarding_progress(
        progress_callback,
        "persist_analysis",
        "正在保存分析结果与候选技能包。",
        {"candidate_skill_pack_count": len(analysis.candidate_skill_packs)},
    )
    persisted_skill_packs = await _upsert_candidate_skill_packs(
        session,
        datasource,
        analysis,
        settings,
        progress_callback=progress_callback,
    )

    profile.summary = _truncate(analysis.datasource_summary, 2000)
    profile.profile_json = merge_profile_runtime_rules(
        profile.profile_json if isinstance(profile.profile_json, dict) else None,
        {
            "schema_snapshot": snapshot_payload,
            "onboarding_profile": rich_profile_payload,
            "onboarding_context": existing_context,
            "analysis": analysis.model_dump(),
        },
    )
    if mode == "failed":
        profile.analysis_status = "analysis_failed"
        profile.analysis_error = str(analysis.profile_highlights.get("llm_error", "LLM 分析失败"))
    else:
        profile.analysis_status = "ready"
        profile.analysis_error = None
    profile.last_analyzed_at = captured_at
    await session.commit()
    await _emit_onboarding_progress(
        progress_callback,
        "finalize",
        "分析结果已落库。",
        {
            "analysis_status": profile.analysis_status,
            "skill_pack_count": len(persisted_skill_packs),
            "unresolved_question_count": len(analysis.unresolved_questions),
        },
    )

    return OnboardingRunResult(
        datasource_id=datasource_id,
        analysis_status=profile.analysis_status,
        summary=profile.summary,
        skill_pack_count=len(persisted_skill_packs),
        unresolved_question_count=len(analysis.unresolved_questions),
        domain_count=len(persisted_skill_packs),
        preview_items=_build_run_preview_items(persisted_skill_packs),
        profile_json=profile.profile_json,
    )
