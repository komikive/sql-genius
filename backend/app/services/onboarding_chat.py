"""Independent conversational assistant for datasource onboarding refinement."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.llm_structured import content_to_text, parse_model_output
from app.db.models.datasource import Datasource
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.onboarding_run import OnboardingRun
from app.services.onboarding_runs import CHAT_RUN_STATUSES

MAX_CONVERSATION_TURNS = 24


class OnboardingChatQuestion(BaseModel):
    prompt: str = Field(..., min_length=1)
    reason: str = Field(default="")
    input_kind: str = Field(default="text")
    options: list[str] = Field(default_factory=list)


class OnboardingChatReply(BaseModel):
    assistant_message: str = Field(..., min_length=1)
    next_question: OnboardingChatQuestion | None = None
    should_rerun_analysis: bool = False


def _coerce_context(profile: DatasourceProfile | None) -> dict[str, Any]:
    if profile is None or not isinstance(profile.profile_json, dict):
        return {}
    raw = profile.profile_json.get("onboarding_context")
    return raw if isinstance(raw, dict) else {}


def _extract_unresolved_questions(profile: DatasourceProfile | None) -> list[dict[str, Any]]:
    if profile is None or not isinstance(profile.profile_json, dict):
        return []
    analysis = profile.profile_json.get("analysis")
    if not isinstance(analysis, dict):
        return []
    items: list[dict[str, Any]] = []
    top_level = analysis.get("unresolved_questions")
    if isinstance(top_level, list):
        items.extend(item for item in top_level if isinstance(item, dict))
    pack_list = analysis.get("candidate_skill_packs")
    if isinstance(pack_list, list):
        for pack in pack_list:
            if not isinstance(pack, dict):
                continue
            open_questions = pack.get("open_questions")
            if isinstance(open_questions, list):
                items.extend(item for item in open_questions if isinstance(item, dict))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        question = str(item.get("question") or "").strip()
        if not question or question in seen:
            continue
        seen.add(question)
        deduped.append(item)
    return deduped


def _extract_answered_questions(context: dict[str, Any]) -> dict[str, str]:
    raw_questions = context.get("questions")
    raw = raw_questions if isinstance(raw_questions, list) else []
    answered: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if question and answer:
            answered[question] = answer
    return answered


def _select_critical_gap_candidates(
    unresolved_questions: list[dict[str, Any]],
    answered_questions: dict[str, str],
) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for item in unresolved_questions:
        question = str(item.get("question") or "").strip()
        if not question or answered_questions.get(question):
            continue
        pending.append(item)

    def _rank(item: dict[str, Any]) -> tuple[int, int]:
        raw_priority = item.get("priority")
        priority = raw_priority if isinstance(raw_priority, int) else 3
        option_bias = 0 if isinstance(item.get("options"), list) and item.get("options") else 1
        return (priority, option_bias)

    return sorted(pending, key=_rank)


def _conversation_text(conversation: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for turn in conversation[-MAX_CONVERSATION_TURNS:]:
        if not isinstance(turn, dict):
            continue
        role = "用户" if turn.get("role") == "user" else "助手"
        content = str(turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_analysis_context_summary(
    *,
    datasource: Datasource,
    profile: DatasourceProfile | None,
    critical_gap_candidates: list[dict[str, Any]],
    answered_questions: dict[str, str],
) -> str:
    summary = (profile.summary if profile else "").strip() or "暂无结构化摘要。"
    lines = [
        f"数据源：{datasource.display_name}（{datasource.dialect}）",
        f"当前画像摘要：{summary}",
    ]
    if answered_questions:
        lines.append(
            "已确认补充信息：\n" + "\n".join(
                f"- {question}: {answer}"
                for question, answer in list(answered_questions.items())[:8]
            )
        )
    if critical_gap_candidates:
        lines.append(
            "仍可能影响结果质量的关键缺口：\n" + "\n".join(
                f"- {str(item.get('question') or '').strip()}"
                + (f" | 原因：{str(item.get('reason') or '').strip()}" if str(item.get("reason") or "").strip() else "")
                for item in critical_gap_candidates[:6]
                if str(item.get("question") or "").strip()
            )
        )
    return "\n\n".join(lines)


async def _generate_reply(
    *,
    datasource: Datasource,
    profile: DatasourceProfile | None,
    context: dict[str, Any],
    conversation: list[dict[str, Any]],
    settings: Settings,
    user_message: str | None,
) -> OnboardingChatReply:
    transcript = _conversation_text(conversation)
    unresolved_questions = _extract_unresolved_questions(profile)
    answered_questions = _extract_answered_questions(context)
    critical_gap_candidates = _select_critical_gap_candidates(unresolved_questions, answered_questions)
    notes = str(context.get("notes") or "")
    raw_saved_answers = context.get("questions")
    saved_answers = raw_saved_answers if isinstance(raw_saved_answers, list) else []
    analysis_context_summary = _build_analysis_context_summary(
        datasource=datasource,
        profile=profile,
        critical_gap_candidates=critical_gap_candidates,
        answered_questions=answered_questions,
    )

    if not (
        settings.sql_agent_chat_api_key
        and settings.sql_agent_chat_base_url
        and settings.sql_agent_chat_model
    ):
        first_question = critical_gap_candidates[0] if critical_gap_candidates else None
        if first_question:
            return OnboardingChatReply(
                assistant_message="我已经先基于现有结构和画像做了初步判断，但还有一个会明显影响技能质量的关键缺口。",
                next_question=OnboardingChatQuestion(
                    prompt=str(first_question.get("question") or "请补充关键信息。"),
                    reason=str(first_question.get("reason") or ""),
                    input_kind=str(first_question.get("input_kind") or "text"),
                    options=[
                        str(item)
                        for item in (first_question.get("options") or [])
                        if isinstance(item, str)
                    ],
                ),
            )
        return OnboardingChatReply(
            assistant_message="基于当前结构和已有补充信息，我没有发现必须先问清楚的关键缺口。可以直接重新分析；如果你知道特殊口径，也可以主动补充。",
            should_rerun_analysis=True,
        )

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
你正在扮演一个“数据源 onboarding 分析助手”，目标是通过多轮中文对话帮助用户补充业务语义，从而让后续技能包生成更准确。

请只返回 JSON，结构如下：
- assistant_message: 你要对用户说的话
- next_question: 如果还需要用户补充，返回 {{prompt, reason, input_kind, options}}，否则为 null
- should_rerun_analysis: 是否建议用户现在重新执行分析

规则：
- 你的默认策略不是提问，而是先基于现有结构、摘要、历史补充和未解问题，自己形成工作判断。
- 只有当某个信息缺口会实质性影响技能包结构、表语义映射、关键业务口径或生成结果质量时，才允许追问。
- 如果没有这种关键缺口，就不要问问题，直接总结你当前已经理解到什么，并建议用户重新分析。
- 每次最多追问一个最重要的问题，不要连续做泛泛的数据源访谈。
- 如果现有未解问题里已经有合适的，就优先沿用并改写得更清晰。
- input_kind 只能是 text、single_select 或 multi_select。
- single_select / multi_select 仅在你已经能给出 2-5 个高质量候选项时使用；否则用 text。
- multi_select 只用于用户可能同时选择多个选项的情况。
- 如果用户刚提供了有价值信息，要先确认你理解了什么，再决定是否继续追问。
- 如果信息已经足够，就明确建议“可以重新分析”。
- 所有输出必须是中文。

数据源：
- id: {datasource.id}
- name: {datasource.display_name}
- dialect: {datasource.dialect}

当前数据源摘要：
{profile.summary if profile else "(暂无)"}

你对当前数据源的工作判断：
{analysis_context_summary}

用户长期补充备注：
{notes or "(暂无)"}

已保存问答：
{json.dumps(saved_answers, ensure_ascii=False)[:4000]}

当前分析识别出的待确认问题：
{json.dumps(critical_gap_candidates, ensure_ascii=False)[:5000]}

最近对话：
{transcript or "(暂无对话)"}

本轮用户最新消息：
{user_message or "(会话开始，请先主动发起引导)"}
"""
    message = await llm.ainvoke(prompt)
    return parse_model_output(OnboardingChatReply, content_to_text(message.content))


async def onboarding_chat_stream(
    session: AsyncSession,
    *,
    datasource_id: str,
    user_message: str | None,
    run_id: str | None,
    settings: Settings,
) -> AsyncIterator[bytes]:
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        yield b"event: done\ndata: {\"ok\": false, \"error\": \"datasource_not_found\"}\n\n"
        return

    profile = await session.get(DatasourceProfile, datasource_id)
    if profile is None:
        profile = DatasourceProfile(datasource_id=datasource_id)
        session.add(profile)
        await session.flush()

    if run_id:
        run = await session.get(OnboardingRun, run_id)
        if run is not None and run.datasource_id != datasource_id:
            run = None
    else:
        run_result = await session.execute(
            select(OnboardingRun)
            .where(OnboardingRun.datasource_id == datasource_id)
            .where(OnboardingRun.status.in_(CHAT_RUN_STATUSES))
            .order_by(OnboardingRun.created_at.desc(), OnboardingRun.id.desc())
            .limit(1)
        )
        run = run_result.scalars().first()
    if run is None:
        yield b"event: done\ndata: {\"ok\": false, \"error\": \"onboarding_run_not_found\"}\n\n"
        return

    context = _coerce_context(profile)
    result_payload = dict(run.result_payload or {}) if isinstance(run.result_payload, dict) else {}
    raw_conversation = result_payload.get("conversation")
    conversation = raw_conversation if isinstance(raw_conversation, list) else []
    if user_message and user_message.strip():
        conversation.append(
            {
                "role": "user",
                "content": user_message.strip(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    yield f"event: step\ndata: {json.dumps({'phase': 'prepare', 'message': '正在整理现有分析上下文。'}, ensure_ascii=False)}\n\n".encode()

    reply = await _generate_reply(
        datasource=datasource,
        profile=profile,
        context=context,
        conversation=conversation,
        settings=settings,
        user_message=user_message.strip() if user_message else None,
    )

    assistant_turn = {
        "role": "assistant",
        "content": reply.assistant_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if reply.next_question is not None:
        assistant_turn["question"] = reply.next_question.model_dump()
    conversation.append(assistant_turn)

    trimmed_conversation = conversation[-MAX_CONVERSATION_TURNS:]
    result_payload["conversation"] = trimmed_conversation
    run.result_payload = result_payload
    await session.commit()

    yield f"event: message\ndata: {json.dumps({'role': 'assistant', 'content': reply.assistant_message}, ensure_ascii=False)}\n\n".encode()
    if reply.next_question is not None:
        yield f"event: question\ndata: {json.dumps(reply.next_question.model_dump(), ensure_ascii=False)}\n\n".encode()
    yield f"event: done\ndata: {json.dumps({'ok': True, 'should_rerun_analysis': reply.should_rerun_analysis}, ensure_ascii=False)}\n\n".encode()
