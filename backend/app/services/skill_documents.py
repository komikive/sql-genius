"""Canonical skill document helpers.

Skill packs act as light-weight indexes. The canonical Markdown document is the
single runtime-readable source of truth for a skill's business method.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.skill_document import SkillDocument
from app.db.models.skill_pack import SkillPack

CANONICAL_SKILL_DOCUMENT_TYPE = "canonical"


def _list_lines(items: list[Any], *, key: str | None = None) -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = str(
                item.get(key or "name")
                or item.get("name")
                or item.get("metric")
                or item.get("rule")
                or item.get("description")
                or ""
            ).strip()
            detail = str(item.get("description") or "").strip()
            if text and detail and detail != text:
                lines.append(f"- {text}：{detail}")
            elif text:
                lines.append(f"- {text}")
        else:
            text = str(item or "").strip()
            if text:
                lines.append(f"- {text}")
    return lines


def render_canonical_skill_document(
    pack: SkillPack,
    *,
    resolved_facts: list[dict[str, Any]] | None = None,
    supplemental_documents: list[dict[str, str]] | None = None,
) -> str:
    """Render one Markdown playbook for a skill pack."""

    sections: list[str] = [f"# {pack.name}"]
    if pack.summary:
        sections.append(f"## 技能摘要\n{pack.summary.strip()}")
    if pack.business_overview:
        sections.append(f"## 业务目标\n{pack.business_overview.strip()}")
    if pack.table_focus:
        sections.append("## 核心表\n" + "\n".join(f"- `{item}`" for item in pack.table_focus if str(item).strip()))
    if pack.schema_notes:
        sections.append(f"## 表结构与 Join 口径\n{pack.schema_notes.strip()}")

    metric_lines = _list_lines(pack.metrics or [], key="name")
    if metric_lines:
        sections.append("## 指标口径\n" + "\n".join(metric_lines))

    entity_lines = _list_lines(pack.entities or [], key="name")
    if entity_lines:
        sections.append("## 关键实体\n" + "\n".join(entity_lines))

    rule_lines = _list_lines(pack.business_rules or [], key="rule")
    if rule_lines:
        sections.append("## 业务规则与易错点\n" + "\n".join(rule_lines))

    fact_lines: list[str] = []
    for item in resolved_facts or []:
        fact = str(item.get("fact") or item.get("answer") or "").strip()
        question = str(item.get("question") or "").strip()
        if fact and question:
            fact_lines.append(f"- {question}：{fact}")
        elif fact:
            fact_lines.append(f"- {fact}")
    if fact_lines:
        sections.append("## 人工补充确认\n" + "\n".join(fact_lines[:16]))

    supplemental_sections: list[str] = []
    for item in supplemental_documents or []:
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if title and content:
            supplemental_sections.append(f"### {title}\n{content}")
        elif content:
            supplemental_sections.append(content)
    if supplemental_sections:
        sections.append("## 补充材料\n" + "\n\n".join(supplemental_sections[:6]))

    if pack.keywords:
        sections.append("## 检索关键词\n" + "\n".join(f"- {item}" for item in pack.keywords if str(item).strip()))

    sections.append(
        "## 使用边界\n"
        "- 本文档只保存稳定的查询方法、业务口径、核心表关系和易错点。\n"
        "- 成功问答与 SQL 示例保存在独立 QA 案例层，不写入技能主文档。\n"
        "- 跨技能通用事实保存在数据源主记忆，不在单个技能内重复维护。"
    )
    return "\n\n".join(section for section in sections if section.strip()).strip()


async def get_canonical_skill_document(
    session: AsyncSession,
    skill_pack_id: str,
) -> SkillDocument | None:
    rows = await session.execute(
        select(SkillDocument)
        .where(SkillDocument.skill_pack_id == skill_pack_id)
        .where(SkillDocument.document_type.in_([CANONICAL_SKILL_DOCUMENT_TYPE, "overview"]))
        .order_by(SkillDocument.weight.desc(), SkillDocument.id.asc())
        .limit(1)
    )
    return rows.scalars().first()


async def upsert_canonical_skill_document(
    session: AsyncSession,
    pack: SkillPack,
    *,
    content: str | None = None,
    resolved_facts: list[dict[str, Any]] | None = None,
    supplemental_documents: list[dict[str, str]] | None = None,
    source: str = "system",
) -> SkillDocument:
    document = await get_canonical_skill_document(session, pack.id)
    if document is None:
        document = SkillDocument(
            skill_pack_id=pack.id,
            document_type=CANONICAL_SKILL_DOCUMENT_TYPE,
            title=f"{pack.name} 技能主文档",
            content="",
            source=source,
            weight=2.0,
            document_metadata={"canonical": True},
            embedding=None,
            embedding_status="pending",
        )
        session.add(document)

    document.document_type = CANONICAL_SKILL_DOCUMENT_TYPE
    document.title = f"{pack.name} 技能主文档"
    document.content = content or render_canonical_skill_document(
        pack,
        resolved_facts=resolved_facts,
        supplemental_documents=supplemental_documents,
    )
    document.source = source
    document.weight = max(float(document.weight or 1.0), 2.0)
    metadata = document.document_metadata if isinstance(document.document_metadata, dict) else {}
    document.document_metadata = {**metadata, "canonical": True}
    document.embedding = None
    document.embedding_status = "pending"
    document.embedding_error = None
    document.embedding_updated_at = None
    await session.flush()
    return document
