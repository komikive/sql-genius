"""Semantic datasource QA example storage and retrieval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.rag.embed_service import build_embedding_client

_QA_SEMANTIC_MERGE_DISTANCE_THRESHOLD = 0.08


def _render_qa_embedding_text(pair: dict[str, Any]) -> str:
    question = str(pair.get("question") or "").strip()
    note = str(pair.get("note") or "").strip()
    tags = "、".join(str(item).strip() for item in (pair.get("scenario_tags") or []) if str(item).strip())
    parts = [question]
    if note:
        parts.append(note)
    if tags:
        parts.append(tags)
    return "\n".join(part for part in parts if part).strip()


async def create_runtime_qa_example(
    session: AsyncSession,
    *,
    datasource_id: str,
    question: str,
    sql: str,
    note: str = "",
    scenario_tags: list[str] | None = None,
    source: str = "runtime-learning",
    skill_pack_id: str | None = None,
    settings: Settings,
) -> DatasourceQaExample:
    """沉淀结构化问答案例到 datasource_qa_examples（与主记忆、技能文档分离）。

    - 同 question 更新 SQL/note；可选向量近邻合并防重复
    - search_qa_examples 工具与 Agent 预检索均读此表
    """

    pair = {
        "question": str(question or "").strip(),
        "sql": str(sql or "").strip(),
        "note": str(note or "").strip(),
        "scenario_tags": [str(item).strip() for item in (scenario_tags or []) if str(item).strip()][:8],
    }
    existing_rows = await session.execute(
        select(DatasourceQaExample)
        .where(DatasourceQaExample.datasource_id == datasource_id)
        .where(DatasourceQaExample.question == pair["question"])
        .order_by(DatasourceQaExample.updated_at.desc(), DatasourceQaExample.id.asc())
        .limit(1)
    )
    row = existing_rows.scalars().first()
    client = build_embedding_client(settings)
    next_embedding: list[float] | None = None
    next_embedding_error: str | None = None
    if client is not None and pair["question"]:
        try:
            next_embedding = await client.aembed_query(_render_qa_embedding_text(pair))
        except Exception as exc:
            next_embedding_error = str(exc)[:300]

    if row is None and next_embedding is not None:
        try:
            distance_expr = DatasourceQaExample.question_embedding.cosine_distance(next_embedding)
            nearest_rows = await session.execute(
                select(DatasourceQaExample, distance_expr.label("distance"))
                .where(DatasourceQaExample.datasource_id == datasource_id)
                .where(DatasourceQaExample.embedding_status == "ready")
                .where(DatasourceQaExample.question_embedding.is_not(None))
                .order_by(distance_expr, DatasourceQaExample.updated_at.desc())
                .limit(1)
            )
            nearest = nearest_rows.first()
            if nearest is not None and float(nearest[1]) <= _QA_SEMANTIC_MERGE_DISTANCE_THRESHOLD:
                row = nearest[0]
        except Exception:
            pass

    if row is None:
        row = DatasourceQaExample(
            datasource_id=datasource_id,
            skill_pack_id=skill_pack_id,
            question=pair["question"],
            sql=pair["sql"],
            note=pair["note"],
            scenario_tags=pair["scenario_tags"],
            source=source,
            source_metadata=None,
            embedding_status="pending",
        )
        session.add(row)
    else:
        row.skill_pack_id = skill_pack_id or row.skill_pack_id
        row.sql = pair["sql"]
        row.note = pair["note"]
        row.scenario_tags = pair["scenario_tags"]
        row.source = source
        row.source_metadata = None
        row.embedding_status = "pending"
        row.embedding_error = None

    if next_embedding is not None and pair["question"]:
        row.question_embedding = next_embedding
        row.embedding_status = "ready"
        row.embedding_error = None
        row.embedding_updated_at = datetime.now(timezone.utc)
    elif next_embedding_error is not None:
        row.question_embedding = None
        row.embedding_status = "error"
        row.embedding_error = next_embedding_error
        row.embedding_updated_at = datetime.now(timezone.utc)
    await session.flush()
    return row


async def search_datasource_qa_examples(
    session: AsyncSession,
    *,
    datasource_id: str,
    query: str,
    settings: Settings,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant datasource QA examples."""

    cooked_limit = max(1, min(int(limit or 5), 10))
    cooked_query = (query or "").strip()
    client = build_embedding_client(settings)
    if client is not None and cooked_query:
        try:
            vector = await client.aembed_query(cooked_query)
            distance_expr = DatasourceQaExample.question_embedding.cosine_distance(vector)
            rows = await session.execute(
                select(DatasourceQaExample, distance_expr.label("distance"))
                .where(DatasourceQaExample.datasource_id == datasource_id)
                .where(DatasourceQaExample.embedding_status == "ready")
                .where(DatasourceQaExample.question_embedding.is_not(None))
                .order_by(distance_expr, DatasourceQaExample.updated_at.desc())
                .limit(cooked_limit)
            )
            mappings = rows.all()
            if mappings:
                return [
                    {
                        "id": row.id,
                        "question": row.question,
                        "sql": row.sql,
                        "note": row.note,
                        "scenario_tags": row.scenario_tags or [],
                        "skill_pack_id": row.skill_pack_id,
                        "distance": float(distance),
                        "score": max(0.0, 1.0 - float(distance) / 2.0),
                    }
                    for row, distance in mappings
                ]
        except Exception:
            pass

    rows = await session.execute(
        select(DatasourceQaExample)
        .where(DatasourceQaExample.datasource_id == datasource_id)
        .order_by(DatasourceQaExample.updated_at.desc())
        .limit(100)
    )
    all_rows = list(rows.scalars().all())
    if not all_rows:
        return []

    query_lower = cooked_query.lower()
    scored: list[tuple[int, DatasourceQaExample]] = []
    for row in all_rows:
        haystack = "\n".join(
            [row.question or "", row.note or "", " ".join(row.scenario_tags or [])]
        ).lower()
        score = 0
        if query_lower and query_lower in haystack:
            score += 4
        for token in query_lower.split():
            if token and token in haystack:
                score += 1
        if not cooked_query:
            score = 1
        scored.append((score, row))
    scored.sort(key=lambda item: (item[0], item[1].updated_at or 0), reverse=True)
    chosen = [row for score, row in scored if score > 0 or not cooked_query][:cooked_limit]
    return [
        {
            "id": row.id,
            "question": row.question,
            "sql": row.sql,
            "note": row.note,
            "scenario_tags": row.scenario_tags or [],
            "skill_pack_id": row.skill_pack_id,
            "distance": None,
            "score": None,
        }
        for row in chosen
    ]
