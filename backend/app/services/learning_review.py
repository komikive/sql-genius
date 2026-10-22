"""Signal-driven post-turn learning review.

Replaces the old "every question creates a skill" approach with:
1. Rule-based pre-filter (no LLM cost for trivial turns)
2. LLM evaluator for memory extraction + skill enrichment
3. New-domain buffering into learning_signals for accumulation
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import AsyncSessionLocal
from app.core.llm_structured import content_to_text, parse_model_output
from app.core.observability import traced
from app.db.models.skill_pack import SkillPack
from app.services.datasource_memory import apply_memory_candidate_to_document
from app.services.qa_examples import create_runtime_qa_example

logger = logging.getLogger(__name__)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SQL_COMPLEXITY_RE = re.compile(
    r"\b(JOIN|GROUP\s+BY|HAVING|UNION|WINDOW|WITH|CASE\s+WHEN|SUBSELECT|EXISTS)\b",
    re.IGNORECASE,
)
# Single-table aggregates (e.g. COUNT/SUM + GROUP BY, or global COUNT) still worth learning.
_SQL_AGGREGATE_RE = re.compile(
    r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(",
    re.IGNORECASE,
)
_QA_MIN_QUESTION_LENGTH = 4
_QA_LOW_SIGNAL_QUESTION_PATTERNS = (
    "看一下",
    "查一下",
    "看看",
    "分析下",
    "分析一下",
    "帮我查",
)


def _slugify(value: str) -> str:
    slug = _NON_ALNUM_RE.sub("-", (value or "").lower()).strip("-")
    return slug or "runtime-learning"


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(limit - 3, 1)] + "..."


def _pattern_hash(datasource_id: str, sql: str) -> str:
    normalized = re.sub(r"\s+", " ", (sql or "").strip().lower())
    return hashlib.sha256(f"{datasource_id}:{normalized}".encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MemoryCandidate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    memory_type: str = Field(default="fact", min_length=1, max_length=32)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    keywords: list[str] = Field(default_factory=list)
    source_excerpt: str = Field(default="")


class SkillExampleSqlPairCandidate(BaseModel):
    question: str = Field(..., min_length=1)
    sql: str = Field(default="")
    note: str = Field(default="")
    scenario_tags: list[str] = Field(default_factory=list)


class SkillEnrichmentProposal(BaseModel):
    target_skill_name: str = Field(..., min_length=1)
    enrichment_type: str = Field(default="example_sql_pair")
    summary: str = Field(default="")
    example_sql_pair: SkillExampleSqlPairCandidate | None = None
    business_rule: dict[str, Any] | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class LearningReviewOutput(BaseModel):
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    skill_enrichments: list[SkillEnrichmentProposal] = Field(default_factory=list)
    new_domain_signal: bool = Field(default=False)
    new_domain_summary: str = Field(default="")


class LearningReviewResult(BaseModel):
    memory_count: int = 0
    memory_updates: list[dict[str, Any]] = Field(default_factory=list)
    qa_example_count: int = 0
    enrichment_count: int = 0
    signal_buffered: bool = False


# ---------------------------------------------------------------------------
# Signal strength pre-filter (no LLM cost)
# ---------------------------------------------------------------------------


def _sql_is_learning_worthy(sql: str | None) -> bool:
    cooked = (sql or "").strip()
    if not cooked:
        return False
    if _SQL_COMPLEXITY_RE.search(cooked):
        return True
    return bool(_SQL_AGGREGATE_RE.search(cooked))


async def _resolve_skill_pack_id(
    session: AsyncSession,
    *,
    datasource_id: str,
    pack_name: str | None,
    activated_skill_pack_names: list[str],
) -> str | None:
    """Pick a skill pack for QA linkage: exact name, then activated list, else None."""
    if pack_name:
        pack_rows = await session.execute(
            select(SkillPack)
            .where(SkillPack.datasource_id == datasource_id)
            .where(SkillPack.name == pack_name)
            .limit(1)
        )
        pack = pack_rows.scalars().first()
        if pack is not None:
            return pack.id

    for name in activated_skill_pack_names:
        pack_rows = await session.execute(
            select(SkillPack)
            .where(SkillPack.datasource_id == datasource_id)
            .where(SkillPack.name == name)
            .limit(1)
        )
        pack = pack_rows.scalars().first()
        if pack is not None:
            return pack.id
    return None


def should_trigger_learning(
    *,
    generated_sql: str | None,
    sql_execution_success: bool,
    user_feedback_positive: bool | None,
    save_to_skill: bool,
) -> bool:
    """Decide whether a turn is worth running through the LLM learning evaluator.

    Returns True only when there is a strong enough learning signal.
    """
    if save_to_skill:
        return True

    if user_feedback_positive is True:
        return True

    if user_feedback_positive is False:
        return False

    if not generated_sql:
        return False

    if not sql_execution_success:
        return False

    if not _sql_is_learning_worthy(generated_sql):
        return False

    return True


def qa_candidate_is_sedimentable(
    *,
    question: str,
    sql: str,
    sql_execution_success: bool,
) -> bool:
    """Sanity-check a runtime QA pair before auto-sedimenting it.

    Keeps the low-signal question filter and SQL complexity guard so we do not
    persist obviously useless pairs. Confidence is no longer gated — once the LLM
    review marks a pair as worth keeping, we sediment it directly.
    """

    cooked_question = _truncate(question or "", 240)
    cooked_sql = (sql or "").strip()
    if not sql_execution_success:
        return False
    if len(cooked_question.strip()) < _QA_MIN_QUESTION_LENGTH:
        return False
    lowered_question = cooked_question.lower()
    if any(marker in lowered_question for marker in _QA_LOW_SIGNAL_QUESTION_PATTERNS):
        return False
    if not _sql_is_learning_worthy(cooked_sql):
        return False
    return True


# ---------------------------------------------------------------------------
# LLM learning evaluator
# ---------------------------------------------------------------------------


async def _llm_learning_output(
    *,
    datasource_id: str,
    user_question: str,
    assistant_text: str,
    generated_sql: str | None,
    sql_explanation: str | None,
    activated_skill_pack_names: list[str],
    settings: Settings,
) -> LearningReviewOutput:
    llm = ChatOpenAI(
        model=settings.sql_agent_chat_model,
        openai_api_key=settings.sql_agent_chat_api_key,
        openai_api_base=settings.sql_agent_chat_base_url,
        temperature=0,
        timeout=120,
        max_retries=1,
        extra_body={"enable_thinking": False},
    )
    prompt = f"""
你是一个面向 Text-to-SQL 系统的后台学习审查器。
请基于本轮成功的问答，判断是否值得提取学习产物，并只返回 JSON。

JSON 结构：
- memory_candidates: 值得跨会话复用的稳定事实，会直接并入数据源主记忆
- skill_enrichments: 建议追加到已有技能包的内容，优先使用结构化 example_sql_pair（问题 + SQL + 说明）
- new_domain_signal: bool，本轮是否涉及一个全新的业务领域（已有技能包无法覆盖）
- new_domain_summary: 如果 new_domain_signal 为 true，简述该新领域

规则：
- memory_candidates：只提取确定性极高、可复用、跨会话稳定的知识。模糊内容不要提取。宁缺勿滥。
- memory_candidates：title 必须使用稳定标题，便于覆盖旧记忆；content 必须是一句极简结论。
- memory_candidates：不要写 SQL、不要写示例问答、不要写临时结果。只保留全局业务口径、关键 schema 模式、查询策略/陷阱。
- skill_enrichments：只要本轮 SQL 已成功执行且值得复用，优先给出 1 条 example_sql_pair（question + sql + note）。
  target_skill_name 尽量填 activated_skill_packs 里的名称；若不确定可填其中最相关的一个。
  如果是 SQL 示例，请使用 example_sql_pair，包含 question、sql、note、scenario_tags。
- 主记忆文档现在由 Agent 自动维护，不要再生成 memory review item。
- new_domain_signal：只有当问题主题完全不属于任何已有技能包时才设为 true。
  不要因为一个简单问题就标记为新领域。
- 如果本轮没有任何值得学习的内容，返回空列表和 false 即可。
- 全部文案请使用中文。

上下文：
- datasource_id: {datasource_id}
- activated_skill_packs: {activated_skill_pack_names}
- user_question: {user_question}
- assistant_text: {assistant_text}
- sql_explanation: {sql_explanation or "(无)"}
- generated_sql: {generated_sql or "(无)"}
"""
    message = await llm.ainvoke(prompt)
    return parse_model_output(LearningReviewOutput, content_to_text(message.content))


async def extract_learning_output(
    *,
    datasource_id: str,
    user_question: str,
    assistant_text: str,
    generated_sql: str | None,
    sql_explanation: str | None,
    activated_skill_pack_names: list[str],
    settings: Settings,
) -> LearningReviewOutput:
    """Extract memory and skill-enrichment proposals from one completed turn.

    Returns empty output if LLM is unavailable or fails -- no heuristic fallback.
    """
    if not (
        settings.sql_agent_chat_api_key
        and settings.sql_agent_chat_base_url
        and settings.sql_agent_chat_model
    ):
        return LearningReviewOutput()

    try:
        return await _llm_learning_output(
            datasource_id=datasource_id,
            user_question=user_question,
            assistant_text=assistant_text,
            generated_sql=generated_sql,
            sql_explanation=sql_explanation,
            activated_skill_pack_names=activated_skill_pack_names,
            settings=settings,
        )
    except Exception:
        logger.exception("runtime learning review llm extraction failed")
        return LearningReviewOutput()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


async def _buffer_learning_signal(
    session: AsyncSession,
    *,
    datasource_id: str,
    thread_id: str | None,
    user_question: str,
    generated_sql: str | None,
    sql_explanation: str | None,
    domain_summary: str,
) -> bool:
    """Buffer a new-domain signal into learning_signals for accumulation."""
    from app.db.models.learning_signal import LearningSignal

    p_hash = _pattern_hash(datasource_id, generated_sql or user_question)

    existing = await session.execute(
        select(LearningSignal)
        .where(LearningSignal.datasource_id == datasource_id)
        .where(LearningSignal.pattern_hash == p_hash)
        .limit(1)
    )
    if existing.scalars().first() is not None:
        return False

    session.add(
        LearningSignal(
            datasource_id=datasource_id,
            thread_id=thread_id,
            user_question=_truncate(user_question, 500),
            generated_sql=_truncate(generated_sql or "", 2000) or None,
            sql_explanation=_truncate(sql_explanation or "", 500) or None,
            domain_summary=_truncate(domain_summary, 500),
            pattern_hash=p_hash,
        )
    )
    await session.flush()
    return True


async def _check_signal_accumulation(
    session: AsyncSession,
    *,
    datasource_id: str,
    threshold: int = 3,
) -> int:
    """Count buffered learning signals for a datasource."""
    from app.db.models.learning_signal import LearningSignal

    result = await session.execute(
        select(func.count(LearningSignal.id))
        .where(LearningSignal.datasource_id == datasource_id)
    )
    return int(result.scalar() or 0)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


@traced("review-post-turn-learning", as_type="chain")
async def run_post_turn_learning_review(
    session: AsyncSession,
    *,
    datasource_id: str,
    thread_id: str | None,
    user_question: str,
    assistant_text: str,
    generated_sql: str | None,
    sql_explanation: str | None,
    activated_skill_pack_names: list[str],
    sql_execution_success: bool = False,
    user_feedback_positive: bool | None = None,
    save_to_skill: bool = False,
    settings: Settings,
) -> LearningReviewResult:
    """回合后学习审查主入口（chat SSE 在 done 前同步调用，反馈接口可后台 spawn）。

    流程：
    1. should_trigger_learning — 规则预筛，避免 trivial turn 调 LLM
    2. extract_learning_output — LLM 产出 memory_candidates / skill_enrichments
    3. 主记忆并入 datasource_memory_documents（同名 title 覆盖）
    4. QA 写入 datasource_qa_examples（无人工审核队列）
    5. enrichments 全失败时 fallback 用本轮 question+SQL 沉淀
    """

    if not datasource_id or not user_question.strip() or not assistant_text.strip():
        return LearningReviewResult()

    # --- 1. 信号门控 ---
    if not should_trigger_learning(
        generated_sql=generated_sql,
        sql_execution_success=sql_execution_success,
        user_feedback_positive=user_feedback_positive,
        save_to_skill=save_to_skill,
    ):
        return LearningReviewResult()

    # --- 2. LLM 评审 ---
    output = await extract_learning_output(
        datasource_id=datasource_id,
        user_question=user_question,
        assistant_text=assistant_text,
        generated_sql=generated_sql,
        sql_explanation=sql_explanation,
        activated_skill_pack_names=activated_skill_pack_names,
        settings=settings,
    )

    # 已有技能命中时不标记「新领域」，避免 learning_signals 噪声
    if activated_skill_pack_names:
        output.new_domain_signal = False
        output.new_domain_summary = ""

    memory_count = 0
    memory_updates: list[dict[str, Any]] = []
    enrichment_count = 0
    qa_example_count = 0
    signal_buffered = False

    # --- 3. 主记忆自动维护 ---
    for candidate in output.memory_candidates:
        applied = await apply_memory_candidate_to_document(
            session,
            datasource_id=datasource_id,
            title=candidate.title,
            content=candidate.content,
            memory_type=candidate.memory_type,
            confidence=float(candidate.confidence),
            settings=settings,
            keywords=candidate.keywords,
            source="runtime-learning",
            source_excerpt=candidate.source_excerpt,
            thread_id=thread_id,
        )
        if bool(applied.get("applied")):
            memory_count += 1
            memory_updates.append(
                {
                    "title": str(applied.get("title") or ""),
                    "content": str(applied.get("content") or ""),
                    "section": str(applied.get("section") or ""),
                    "action": str(applied.get("action") or "updated"),
                    "confidence": float(applied.get("confidence") or 0.0),
                    "change_summary": str(applied.get("change_summary") or ""),
                    "updated_at": str(applied.get("updated_at") or ""),
                }
            )

    # --- 4. 技能 enrichments → 独立 QA 层 ---
    for proposal in output.skill_enrichments:
        if (
            proposal.enrichment_type != "example_sql_pair"
            or proposal.example_sql_pair is None
        ):
            continue
        pair = proposal.example_sql_pair
        pair_sql = (pair.sql or "").strip() or (generated_sql or "").strip()
        pair_question = (pair.question or "").strip() or user_question
        if not pair_sql:
            continue
        if not qa_candidate_is_sedimentable(
            question=pair_question,
            sql=pair_sql,
            sql_execution_success=sql_execution_success,
        ):
            continue
        skill_pack_id = await _resolve_skill_pack_id(
            session,
            datasource_id=datasource_id,
            pack_name=proposal.target_skill_name,
            activated_skill_pack_names=activated_skill_pack_names,
        )
        await create_runtime_qa_example(
            session,
            datasource_id=datasource_id,
            skill_pack_id=skill_pack_id,
            question=pair_question,
            sql=pair_sql,
            note=pair.note or sql_explanation or "运行时学习审查沉淀的 SQL 案例。",
            scenario_tags=pair.scenario_tags,
            source="runtime-learning",
            settings=settings,
        )
        enrichment_count += 1
        qa_example_count += 1

    # --- 5. 兜底沉淀（答辩常问：为何有时没 enrichment 仍有 QA）---
    if (
        qa_example_count == 0
        and generated_sql
        and sql_execution_success
        and qa_candidate_is_sedimentable(
            question=user_question,
            sql=generated_sql,
            sql_execution_success=sql_execution_success,
        )
    ):
        fallback_pack_id = await _resolve_skill_pack_id(
            session,
            datasource_id=datasource_id,
            pack_name=None,
            activated_skill_pack_names=activated_skill_pack_names,
        )
        await create_runtime_qa_example(
            session,
            datasource_id=datasource_id,
            skill_pack_id=fallback_pack_id,
            question=user_question,
            sql=generated_sql,
            note=sql_explanation or "运行时自动沉淀的高价值 SQL 案例。",
            scenario_tags=[],
            source="runtime-learning",
            settings=settings,
        )
        enrichment_count += 1
        qa_example_count += 1

    # --- 6. 新领域信号缓冲（累计后再考虑扩展技能包）---
    if output.new_domain_signal and output.new_domain_summary:
        buffered = await _buffer_learning_signal(
            session,
            datasource_id=datasource_id,
            thread_id=thread_id,
            user_question=user_question,
            generated_sql=generated_sql,
            sql_explanation=sql_explanation,
            domain_summary=output.new_domain_summary,
        )
        signal_buffered = buffered

    await session.flush()
    return LearningReviewResult(
        memory_count=memory_count,
        memory_updates=memory_updates,
        qa_example_count=qa_example_count,
        enrichment_count=enrichment_count,
        signal_buffered=signal_buffered,
    )


def spawn_post_turn_learning_review(
    *,
    datasource_id: str,
    thread_id: str | None,
    user_question: str,
    assistant_text: str,
    generated_sql: str | None,
    sql_explanation: str | None,
    activated_skill_pack_names: list[str],
    sql_execution_success: bool = False,
    user_feedback_positive: bool | None = None,
    save_to_skill: bool = False,
) -> None:
    """后台触发学习审查（如 submit_turn_feedback），不阻塞 HTTP 响应。

    chat SSE 路径在 _stream_chat_events 内同步调用 run_post_turn_learning_review，
    以便 Workbench 在 done 前展示 memory_autoupdate。
    """

    async def _runner() -> None:
        settings = get_settings()
        try:
            async with AsyncSessionLocal() as session:
                await run_post_turn_learning_review(
                    session,
                    datasource_id=datasource_id,
                    thread_id=thread_id,
                    user_question=user_question,
                    assistant_text=assistant_text,
                    generated_sql=generated_sql,
                    sql_explanation=sql_explanation,
                    activated_skill_pack_names=activated_skill_pack_names,
                    sql_execution_success=sql_execution_success,
                    user_feedback_positive=user_feedback_positive,
                    save_to_skill=save_to_skill,
                    settings=settings,
                )
                await session.commit()
        except Exception:
            logger.exception("background post-turn learning review failed")

    try:
        asyncio.get_running_loop().create_task(_runner())
    except RuntimeError:
        logger.warning("skipped background learning review because no running event loop exists")
