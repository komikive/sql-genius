"""Autonomously managed datasource memory document helpers and recall logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.datasource import Datasource
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.datasource_profile import DatasourceProfile

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_RE = re.compile(
    r"^-\s+(?:\*\*(?P<title>.+?)\*\*[：:]?\s*)?(?P<content>.+?)\s*$"
)

_BUSINESS_SECTION = "全局业务口径"
_SCHEMA_SECTION = "关键 Schema 模式"
_STRATEGY_SECTION = "查询策略与注意事项"
_OTHER_SECTION = "其他全局知识"
_SECTION_ORDER = [
    _BUSINESS_SECTION,
    _SCHEMA_SECTION,
    _STRATEGY_SECTION,
    _OTHER_SECTION,
]
_SECTION_INDEX = {name: index for index, name in enumerate(_SECTION_ORDER)}
_DEFAULT_MEMORY_DOC_CHAR_BUDGET = 3000
_DEFAULT_MEMORY_ITEM_LIMIT = 14
_UPDATE_TRACE_LIMIT = 12
_TEMPORAL_MEMORY_MARKERS = (
    "今天",
    "昨日",
    "昨天",
    "本周",
    "上周",
    "本月",
    "上月",
    "今年",
    "去年",
    "最近",
    "近7天",
    "近30天",
    "过去",
    "latest",
    "today",
    "yesterday",
    "this week",
    "last week",
    "this month",
    "last month",
)


@dataclass(slots=True)
class RecalledMemoryChunk:
    """Prompt-friendly chunk recalled from the canonical memory document."""

    id: str
    title: str
    content: str
    section: str
    keywords: list[str]


@dataclass(slots=True)
class MemoryDocumentItem:
    """One concise persistent fact stored inside the autonomous memory document."""

    title: str
    content: str
    memory_type: str
    section: str
    confidence: float = 0.0
    keywords: list[str] = field(default_factory=list)
    source: str | None = None
    source_excerpt: str | None = None
    thread_id: str | None = None
    updated_at: str | None = None


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "") if token.strip()}


def _truncate(value: str, limit: int = 320) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)] + "..."


def _normalize_section(title: str) -> str:
    text = str(title or "").strip()
    lowered = text.lower()
    if "schema" in lowered or any(token in text for token in ("表", "字段", "关联", "关系", "主键", "外键")):
        return _SCHEMA_SECTION
    if any(token in lowered for token in ("query", "sql", "strategy", "pitfall", "guardrail", "filter")):
        return _STRATEGY_SECTION
    if any(token in text for token in ("策略", "注意", "过滤", "口径陷阱", "时间字段", "查询")):
        return _STRATEGY_SECTION
    if any(token in text for token in ("业务", "口径", "规则", "指标")):
        return _BUSINESS_SECTION
    return _OTHER_SECTION


def _section_for_memory_type(memory_type: str) -> str:
    lowered = str(memory_type or "").strip().lower()
    if any(token in lowered for token in ("schema", "table", "column", "field", "join", "relation")):
        return _SCHEMA_SECTION
    if any(token in lowered for token in ("query", "sql", "strategy", "pitfall", "guardrail", "filter")):
        return _STRATEGY_SECTION
    if any(token in lowered for token in ("rule", "fact", "metric", "business", "definition", "global")):
        return _BUSINESS_SECTION
    return _OTHER_SECTION


def _normalize_memory_title(value: str) -> str:
    title = _truncate(str(value or "").replace("\n", " ").strip(), 36)
    return title.strip("：:;；,.，。")


def _normalize_memory_content(value: str) -> str:
    content = _truncate(str(value or "").replace("\n", " ").strip(), 120)
    return content.strip("：:;；")


def _serialize_memory_item(item: MemoryDocumentItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "content": item.content,
        "memory_type": item.memory_type,
        "section": item.section,
        "confidence": float(item.confidence or 0.0),
        "keywords": item.keywords[:8],
        "source": item.source,
        "source_excerpt": item.source_excerpt,
        "thread_id": item.thread_id,
        "updated_at": item.updated_at,
    }


def _deserialize_memory_item(payload: Any) -> MemoryDocumentItem | None:
    if not isinstance(payload, dict):
        return None
    title = _normalize_memory_title(payload.get("title") or "")
    content = _normalize_memory_content(payload.get("content") or "")
    if not title or not content or content == "暂无稳定条目。":
        return None
    memory_type = _truncate(str(payload.get("memory_type") or "global-fact"), 32)
    section = _normalize_section(payload.get("section") or _section_for_memory_type(memory_type))
    keywords = [
        str(item).strip()
        for item in (payload.get("keywords") or [])
        if str(item).strip()
    ][:8]
    return MemoryDocumentItem(
        title=title,
        content=content,
        memory_type=memory_type,
        section=section,
        confidence=float(payload.get("confidence") or 0.0),
        keywords=keywords,
        source=_truncate(str(payload.get("source") or "").strip(), 64) or None,
        source_excerpt=_truncate(str(payload.get("source_excerpt") or "").strip(), 200) or None,
        thread_id=_truncate(str(payload.get("thread_id") or "").strip(), 128) or None,
        updated_at=_truncate(str(payload.get("updated_at") or "").strip(), 64) or None,
    )


def _load_document_items(document: DatasourceMemoryDocument) -> list[MemoryDocumentItem]:
    """Load canonical memory items, preferring structured metadata over markdown parsing."""

    metadata = dict(document.document_metadata or {})
    stored_items = metadata.get("memory_items") if isinstance(metadata.get("memory_items"), list) else []
    items = [
        item
        for item in (_deserialize_memory_item(payload) for payload in stored_items)
        if item is not None
    ]
    if items:
        return _prune_memory_items(items)
    fallback_items = _extract_memory_items_from_markdown(document.markdown_content)
    return _prune_memory_items(fallback_items)


def _looks_like_ephemeral_observation(title: str, content: str) -> bool:
    text = f"{title} {content}".lower()
    return any(marker.lower() in text for marker in _TEMPORAL_MEMORY_MARKERS)


def _looks_like_query_result(title: str, content: str) -> bool:
    lowered = f"{title} {content}".lower()
    if "select " in lowered or " from " in lowered or " group by " in lowered:
        return True
    if any(token in lowered for token in ("返回", "查询结果", "共 ", "total_returned", "rows", "行数据")):
        return True
    return False


def _memory_candidate_guardrail_reason(title: str, content: str, memory_type: str) -> str | None:
    cooked_title = str(title or "").strip()
    cooked_content = str(content or "").strip()
    lowered_type = str(memory_type or "").strip().lower()
    if _looks_like_query_result(cooked_title, cooked_content):
        return "query_result_like"
    if _looks_like_ephemeral_observation(cooked_title, cooked_content):
        return "ephemeral_time_bound"
    if lowered_type in {"example", "example-sql", "sql-example", "qa-pair", "question", "result"}:
        return "memory_type_not_allowed"
    return None


def build_memory_outline(markdown_content: str) -> list[dict[str, Any]]:
    """Build a lightweight outline from markdown headings."""

    outline: list[dict[str, Any]] = []
    for line in (markdown_content or "").splitlines():
        match = _HEADING_RE.match(line.strip())
        if not match:
            continue
        hashes, title = match.groups()
        outline.append({"level": len(hashes), "title": title.strip()})
    return outline[:24]


def _split_markdown_sections(markdown_content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "总览"
    buffer: list[str] = []

    for raw_line in (markdown_content or "").splitlines():
        line = raw_line.rstrip()
        match = _HEADING_RE.match(line.strip())
        if match:
            content = "\n".join(buffer).strip()
            if content:
                sections.append((current_title, content))
            current_title = match.group(2).strip()
            buffer = []
            continue
        buffer.append(line)

    tail = "\n".join(buffer).strip()
    if tail:
        sections.append((current_title, tail))

    if not sections and markdown_content.strip():
        sections.append(("主记忆", markdown_content.strip()))
    return sections


def _is_placeholder_line(text: str) -> bool:
    cooked = str(text or "").strip()
    return not cooked or cooked in {"暂无稳定条目。", "暂无稳定条目", "_当前主记忆为空_"}


def _extract_memory_items_from_markdown(markdown_content: str) -> list[MemoryDocumentItem]:
    items: list[MemoryDocumentItem] = []
    sections = _split_markdown_sections(markdown_content)
    for raw_title, raw_content in sections:
        section_title = _normalize_section(raw_title)
        lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
        bullet_found = False
        for line in lines:
            match = _BULLET_RE.match(line)
            if not match:
                continue
            bullet_found = True
            title = _normalize_memory_title(match.group("title") or match.group("content") or "")
            content = _normalize_memory_content(match.group("content") or "")
            if not title or _is_placeholder_line(content):
                continue
            items.append(
                MemoryDocumentItem(
                    title=title,
                    content=content,
                    memory_type="migrated",
                    section=section_title,
                )
            )
        if bullet_found:
            continue

        paragraph = _normalize_memory_content(" ".join(lines))
        if (
            not paragraph
            or "管理员" in paragraph
            or "人工维护" in paragraph
            or "手动维护" in paragraph
            or "运行时学习不会再自动写入" in paragraph
        ):
            continue
        items.append(
            MemoryDocumentItem(
                title=_normalize_memory_title(raw_title or "补充知识"),
                content=paragraph,
                memory_type="migrated",
                section=section_title,
            )
        )
    return items


def _item_rank(item: MemoryDocumentItem) -> tuple[float, str, str]:
    return (
        float(item.confidence or 0.0),
        str(item.updated_at or ""),
        item.title.lower(),
    )


def _dedupe_memory_items(items: list[MemoryDocumentItem]) -> list[MemoryDocumentItem]:
    best: dict[tuple[str, str], MemoryDocumentItem] = {}
    for item in items:
        key = (item.section.lower(), item.title.lower())
        current = best.get(key)
        if current is None or _item_rank(item) >= _item_rank(current):
            best[key] = item
    return list(best.values())


def _prune_memory_items(
    items: list[MemoryDocumentItem],
    *,
    char_budget: int = _DEFAULT_MEMORY_DOC_CHAR_BUDGET,
    max_items: int = _DEFAULT_MEMORY_ITEM_LIMIT,
) -> list[MemoryDocumentItem]:
    deduped = _dedupe_memory_items(items)
    ranked = sorted(deduped, key=_item_rank, reverse=True)[:max_items]
    while ranked and len(render_memory_items_markdown("memory", ranked)) > char_budget:
        ranked.pop()
    return ranked


def _sort_items_for_render(items: list[MemoryDocumentItem]) -> list[MemoryDocumentItem]:
    return sorted(
        items,
        key=lambda item: (
            _SECTION_INDEX.get(item.section, len(_SECTION_ORDER)),
            -float(item.confidence or 0.0),
            str(item.updated_at or ""),
            item.title.lower(),
        ),
        reverse=False,
    )


def render_memory_items_markdown(
    datasource_name: str,
    items: list[MemoryDocumentItem],
) -> str:
    sections = [f"# {datasource_name} 主记忆"]
    rendered_items = _sort_items_for_render(items)
    for section in _SECTION_ORDER:
        section_items = [item for item in rendered_items if item.section == section]
        if not section_items:
            continue
        lines = [f"- **{item.title}**：{item.content}" for item in section_items]
        sections.append(f"## {section}\n" + "\n".join(lines))
    if len(sections) == 1:
        sections.append("## 全局业务口径\n- 暂无稳定条目。")
    return "\n\n".join(section.strip() for section in sections if section.strip()).strip()


def build_memory_source_overview(
    *,
    profile_summary: str | None,
) -> str:
    parts = ["主记忆由 Agent 基于高置信稳定信号自动维护。"]
    parts.append("每次只保留极简条目，不保存零散过程性内容。")
    if (profile_summary or "").strip():
        parts.append("冷启动时参考了数据源画像摘要。")
    parts.append("SQL 问答对继续沉淀到 Skills，不进入主记忆。")
    return " ".join(parts)


def get_recent_memory_updates(document: DatasourceMemoryDocument) -> list[dict[str, Any]]:
    metadata = dict(document.document_metadata or {})
    rows = metadata.get("recent_updates") if isinstance(metadata.get("recent_updates"), list) else []
    updates: list[dict[str, Any]] = []
    for row in rows[:_UPDATE_TRACE_LIMIT]:
        if not isinstance(row, dict):
            continue
        updates.append(
            {
                "title": _normalize_memory_title(row.get("title") or ""),
                "content": _normalize_memory_content(row.get("content") or ""),
                "memory_type": _truncate(str(row.get("memory_type") or "fact"), 32),
                "section": _normalize_section(row.get("section") or row.get("memory_type") or ""),
                "action": _truncate(str(row.get("action") or "updated"), 32),
                "source": _truncate(str(row.get("source") or "runtime-learning"), 64),
                "change_summary": _truncate(str(row.get("change_summary") or "").strip(), 200) or None,
                "confidence": float(row.get("confidence") or 0.0),
                "source_excerpt": _truncate(str(row.get("source_excerpt") or "").strip(), 240) or None,
                "thread_id": _truncate(str(row.get("thread_id") or "").strip(), 128) or None,
                "updated_at": _truncate(str(row.get("updated_at") or "").strip(), 64) or None,
            }
        )
    return updates


async def ensure_datasource_memory_document(
    session: AsyncSession,
    *,
    datasource_id: str,
) -> DatasourceMemoryDocument:
    """Load or create the canonical memory document for one datasource."""

    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise ValueError("datasource_not_found")

    profile_summary = await session.scalar(
        select(DatasourceProfile.summary).where(DatasourceProfile.datasource_id == datasource_id)
    )
    document = await session.get(DatasourceMemoryDocument, datasource_id)
    if document is None:
        seed_items: list[MemoryDocumentItem] = []
        markdown_content = render_memory_items_markdown(datasource.display_name, seed_items)
        document = DatasourceMemoryDocument(
            datasource_id=datasource_id,
            title=f"{datasource.display_name} 主记忆",
            markdown_content=markdown_content,
            source_overview=build_memory_source_overview(
                profile_summary=profile_summary,
            ),
            structured_outline=build_memory_outline(markdown_content),
            document_metadata={
                "management_mode": "agent-managed",
                "source_of_truth": "memory_items",
                "memory_items": [_serialize_memory_item(item) for item in seed_items],
                "item_count": len(seed_items),
                "recent_updates": [],
                "initialized_from_profile_summary": bool((profile_summary or "").strip()),
                "usage_count": 0,
            },
        )
        session.add(document)
        await session.flush()
        return document

    metadata = dict(document.document_metadata or {})
    parsed_items = _load_document_items(document)
    rendered_markdown = render_memory_items_markdown(datasource.display_name, parsed_items)

    needs_refresh = (
        metadata.get("management_mode") != "agent-managed"
        or metadata.get("source_of_truth") != "memory_items"
        or metadata.get("item_count") != len(parsed_items)
        or document.structured_outline is None
        or not (document.source_overview or "").strip()
        or (document.markdown_content or "").strip() != rendered_markdown.strip()
    )
    if needs_refresh:
        metadata.update(
            {
                "management_mode": "agent-managed",
                "source_of_truth": "memory_items",
                "memory_items": [_serialize_memory_item(item) for item in parsed_items],
                "item_count": len(parsed_items),
            }
        )
        metadata.setdefault("recent_updates", [])
        metadata.setdefault("usage_count", 0)
        metadata.setdefault("initialized_from_profile_summary", bool((profile_summary or "").strip()))
        document.markdown_content = rendered_markdown
        document.source_overview = build_memory_source_overview(
            profile_summary=profile_summary,
        )
        document.structured_outline = build_memory_outline(rendered_markdown)
        document.document_metadata = metadata
        await session.flush()
    return document


async def apply_memory_candidate_to_document(
    session: AsyncSession,
    *,
    datasource_id: str,
    title: str,
    content: str,
    memory_type: str,
    confidence: float,
    settings: Settings,
    keywords: list[str] | None = None,
    source: str = "runtime-learning",
    source_excerpt: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """将一条稳定事实写入数据源主记忆 Markdown（Agent 工具 / 回合后学习共用）。

    - 同名同 section 条目覆盖（action=replaced）
    - guardrail 拒绝 SQL 片段、临时结果、低信号文案
    - document_metadata.recent_updates 供 Admin / Memory 可观测
    """

    cooked_title = _normalize_memory_title(title)
    cooked_content = _normalize_memory_content(content)
    if not cooked_title or not cooked_content:
        return {"applied": False, "reason": "empty_candidate"}
    guardrail_reason = _memory_candidate_guardrail_reason(cooked_title, cooked_content, memory_type)
    if guardrail_reason:
        return {"applied": False, "reason": guardrail_reason}

    document = await ensure_datasource_memory_document(session, datasource_id=datasource_id)
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise ValueError("datasource_not_found")

    metadata = dict(document.document_metadata or {})
    items = _load_document_items(document)

    section = _section_for_memory_type(memory_type)
    now_iso = datetime.now(timezone.utc).isoformat()
    candidate = MemoryDocumentItem(
        title=cooked_title,
        content=cooked_content,
        memory_type=_truncate(memory_type or "global-fact", 32),
        section=section,
        confidence=float(confidence or 0.0),
        keywords=[str(item).strip() for item in (keywords or []) if str(item).strip()][:8],
        source=_truncate(source, 64) or "runtime-learning",
        source_excerpt=_truncate(source_excerpt or "", 200) or None,
        thread_id=_truncate(thread_id or "", 128) or None,
        updated_at=now_iso,
    )

    action = "added"
    change_summary = "补充新的稳定知识条目。"
    for index, item in enumerate(items):
        if item.section.lower() == candidate.section.lower() and item.title.lower() == candidate.title.lower():
            items[index] = candidate
            action = "replaced"
            change_summary = "按最新高置信结论改写同名条目。"
            break
    else:
        items.append(candidate)

    items = _prune_memory_items(
        items,
        char_budget=max(800, int(settings.sql_agent_datasource_memory_char_budget)),
        max_items=_DEFAULT_MEMORY_ITEM_LIMIT,
    )
    markdown_content = render_memory_items_markdown(datasource.display_name, items)

    recent_updates = get_recent_memory_updates(document)
    recent_updates.insert(
        0,
        {
            "title": candidate.title,
            "content": candidate.content,
            "memory_type": candidate.memory_type,
            "section": candidate.section,
            "action": action,
            "source": candidate.source,
            "change_summary": change_summary,
            "confidence": candidate.confidence,
            "source_excerpt": candidate.source_excerpt,
            "thread_id": candidate.thread_id,
            "updated_at": now_iso,
        },
    )

    metadata.update(
        {
            "management_mode": "agent-managed",
            "source_of_truth": "memory_items",
            "memory_items": [_serialize_memory_item(item) for item in items],
            "item_count": len(items),
            "recent_updates": recent_updates[:_UPDATE_TRACE_LIMIT],
            "last_autonomous_update_at": now_iso,
            "last_autonomous_update_source": candidate.source,
        }
    )
    metadata.setdefault("usage_count", 0)

    document.markdown_content = markdown_content
    document.structured_outline = build_memory_outline(markdown_content)
    document.document_metadata = metadata
    await session.flush()
    return {
        "applied": True,
        "action": action,
        "section": candidate.section,
        "title": candidate.title,
        "content": candidate.content,
        "confidence": candidate.confidence,
        "change_summary": change_summary,
        "updated_at": now_iso,
    }


async def recall_datasource_memory(
    session: AsyncSession,
    *,
    datasource_id: str,
    query: str,
    settings: Settings,
    limit: int = 6,
) -> list[RecalledMemoryChunk]:
    """按用户问题召回主记忆条目（prepare_runtime 与 recall_memory 工具）。

    评分结合 section 权重、关键词命中、标题相似度；不含 SQL 示例（走 QA 层）。
    """

    document = await ensure_datasource_memory_document(session, datasource_id=datasource_id)
    items = _load_document_items(document)
    if not items:
        return []

    char_budget = max(400, int(settings.sql_agent_runtime_memory_char_budget))
    scored = [
        (
            RecalledMemoryChunk(
                id=f"{datasource_id}:{index}:{item.section}:{item.title}",
                title=item.title,
                content=item.content.strip(),
                section=item.section,
                keywords=(item.keywords or list(_tokenize(f"{item.title} {item.content}"))[:8])[:8],
            ),
            _item_score(item, query),
        )
        for index, item in enumerate(items, start=1)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    scored = [item for item in scored if item[1] > 0 or not query.strip()] or scored[:1]
    return _choose_chunks_with_budget(
        scored,
        limit=max(1, limit),
        char_budget=char_budget,
    )


def _item_score(item: MemoryDocumentItem, query: str) -> float:
    query_terms = _tokenize(query)
    raw_query = str(query or "").strip().lower()
    if not query_terms and not raw_query:
        return max(1.0, float(item.confidence or 0.0))
    haystack = f"{item.section}\n{item.title}\n{item.content}\n{' '.join(item.keywords or [])}"
    hay_terms = _tokenize(haystack)
    overlap = len(query_terms & hay_terms)
    title_bonus = 0.75 if query_terms & _tokenize(item.title) else 0.0
    section_bonus = 0.25 if query_terms & _tokenize(item.section) else 0.0
    confidence_bonus = min(max(float(item.confidence or 0.0), 0.0), 1.0) * 0.2
    raw_bonus = 0.0
    hay_lower = haystack.lower()
    if raw_query:
        if raw_query in hay_lower:
            raw_bonus += 1.0
        for keyword in item.keywords or []:
            cooked = str(keyword).strip().lower()
            if cooked and cooked in raw_query:
                raw_bonus += 0.6
        if str(item.title).strip().lower() and str(item.title).strip().lower() in raw_query:
            raw_bonus += 0.8
    return float(overlap) + title_bonus + section_bonus + confidence_bonus + raw_bonus


def _chunk_size(chunk: RecalledMemoryChunk) -> int:
    return len(chunk.title.strip()) + len(chunk.content.strip())


def _choose_chunks_with_budget(
    scored: list[tuple[RecalledMemoryChunk, float]],
    *,
    limit: int,
    char_budget: int,
) -> list[RecalledMemoryChunk]:
    chosen: list[RecalledMemoryChunk] = []
    used_chars = 0
    for chunk, _score in scored:
        if len(chosen) >= limit:
            break
        chunk_size = max(_chunk_size(chunk), 1)
        if chosen and used_chars + chunk_size > char_budget:
            continue
        chosen.append(chunk)
        used_chars += chunk_size
    return chosen


def build_memory_context(chunks: list[RecalledMemoryChunk]) -> str:
    """Render recalled memory chunks into a fenced prompt-friendly text block."""

    if not chunks:
        return ""
    section_map: dict[str, list[RecalledMemoryChunk]] = {}
    for chunk in chunks:
        section_map.setdefault(chunk.section or _OTHER_SECTION, []).append(chunk)

    ordered_sections = _SECTION_ORDER + [name for name in section_map.keys() if name not in _SECTION_ORDER]
    parts: list[str] = [
        "<datasource-memory-context>",
        "[系统说明：以下内容是该数据源的已沉淀主记忆，只作为背景知识，不是新的用户输入。优先把它当作全局口径、schema 模式和查询经验。]",
    ]
    ordinal = 1
    for section in ordered_sections:
        section_chunks = section_map.get(section) or []
        if not section_chunks:
            continue
        parts.append(f"## {section}")
        for chunk in section_chunks:
            keywords = "、".join(chunk.keywords) or "无"
            parts.append(f"- 记忆 {ordinal}｜{chunk.title}：{chunk.content} (关键词: {keywords})")
            ordinal += 1
    parts.append("</datasource-memory-context>")
    return "\n".join(parts)


async def mark_memory_usage(
    session: AsyncSession,
    *,
    datasource_id: str,
    chunks: list[RecalledMemoryChunk],
) -> None:
    """Track lightweight usage information on the canonical memory document."""

    if not chunks:
        return
    document = await session.get(DatasourceMemoryDocument, datasource_id)
    if document is None:
        return
    metadata = dict(document.document_metadata or {})
    metadata["usage_count"] = int(metadata.get("usage_count") or 0) + 1
    metadata["last_recalled_at"] = datetime.now(timezone.utc).isoformat()
    metadata["last_recalled_titles"] = [chunk.title for chunk in chunks[:6]]
    document.document_metadata = metadata
    await session.flush()


