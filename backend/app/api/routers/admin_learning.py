"""Admin APIs for datasource memory, QA examples, and thread summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_qa_example import DatasourceQaExample
from app.db.models.thread_context_summary import ThreadContextSummary
from app.services.datasource_memory import (
    build_memory_outline,
    ensure_datasource_memory_document,
    get_recent_memory_updates,
)

router = APIRouter()


class AdminDatasourceMemoryEvidence(BaseModel):
    kind: str
    title: str
    excerpt: str
    updated_at: datetime | None = None


class AdminDatasourceMemoryUpdateTrace(BaseModel):
    title: str
    content: str
    memory_type: str
    section: str
    action: str
    source: str
    change_summary: str | None = None
    confidence: float
    source_excerpt: str | None = None
    thread_id: str | None = None
    updated_at: datetime | None = None


class AdminDatasourceMemoryDocumentResponse(BaseModel):
    datasource_id: str
    title: str
    markdown_content: str
    source_overview: str | None = None
    structured_outline: list[dict[str, Any]]
    document_metadata: dict[str, Any] | None = None
    management_mode: str
    item_count: int
    recent_updates: list[AdminDatasourceMemoryUpdateTrace]
    evidence_items: list[AdminDatasourceMemoryEvidence]
    created_at: datetime
    updated_at: datetime


class AdminDatasourceMemoryDocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    markdown_content: str | None = None
    source_overview: str | None = None


class AdminDatasourceQaExampleResponse(BaseModel):
    id: str
    datasource_id: str
    skill_pack_id: str | None = None
    question: str
    sql: str
    note: str
    scenario_tags: list[str]
    source: str
    source_metadata: dict[str, Any] | None = None
    embedding_status: str
    embedding_error: str | None = None
    embedding_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminDatasourceQaExampleListResponse(BaseModel):
    items: list[AdminDatasourceQaExampleResponse]


class AdminThreadSummaryResponse(BaseModel):
    thread_id: str
    datasource_id: str
    rolling_summary: str
    summary_status: str
    char_count: int
    recent_turn_count: int
    summarized_turn_count: int
    compression_count: int
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    last_compacted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminThreadSummaryListResponse(BaseModel):
    items: list[AdminThreadSummaryResponse]


def _qa_response(row: DatasourceQaExample) -> AdminDatasourceQaExampleResponse:
    return AdminDatasourceQaExampleResponse(
        id=row.id,
        datasource_id=row.datasource_id,
        skill_pack_id=row.skill_pack_id,
        question=row.question,
        sql=row.sql,
        note=row.note,
        scenario_tags=row.scenario_tags or [],
        source=row.source,
        source_metadata=row.source_metadata,
        embedding_status=row.embedding_status,
        embedding_error=row.embedding_error,
        embedding_updated_at=row.embedding_updated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _memory_document_response(
    session: AsyncSession,
    row: DatasourceMemoryDocument,
) -> AdminDatasourceMemoryDocumentResponse:
    evidence_items: list[AdminDatasourceMemoryEvidence] = []

    profile = await session.get(DatasourceProfile, row.datasource_id)
    if profile is not None and (profile.summary or "").strip():
        evidence_items.append(
            AdminDatasourceMemoryEvidence(
                kind="datasource-profile",
                title="数据源画像摘要",
                excerpt=profile.summary.strip()[:1200],
                updated_at=profile.updated_at,
            )
        )

    return AdminDatasourceMemoryDocumentResponse(
        datasource_id=row.datasource_id,
        title=row.title,
        markdown_content=row.markdown_content,
        source_overview=row.source_overview,
        structured_outline=row.structured_outline or build_memory_outline(row.markdown_content),
        document_metadata=row.document_metadata,
        management_mode=str((row.document_metadata or {}).get("management_mode") or "agent-managed"),
        item_count=int((row.document_metadata or {}).get("item_count") or 0),
        recent_updates=[
            AdminDatasourceMemoryUpdateTrace(**item)
            for item in get_recent_memory_updates(row)
        ],
        evidence_items=evidence_items,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _summary_response(row: ThreadContextSummary) -> AdminThreadSummaryResponse:
    return AdminThreadSummaryResponse(
        thread_id=row.thread_id,
        datasource_id=row.datasource_id,
        rolling_summary=row.rolling_summary,
        summary_status=row.summary_status,
        char_count=int(row.char_count or 0),
        recent_turn_count=int(row.recent_turn_count or 0),
        summarized_turn_count=int(row.summarized_turn_count or 0),
        compression_count=int(row.compression_count or 0),
        last_user_message=row.last_user_message,
        last_assistant_message=row.last_assistant_message,
        last_compacted_at=row.last_compacted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/admin/datasources/{datasource_id}/memory-document",
    response_model=AdminDatasourceMemoryDocumentResponse,
)
async def get_admin_memory_document(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceMemoryDocumentResponse:
    try:
        row = await ensure_datasource_memory_document(
            session,
            datasource_id=datasource_id,
        )
    except ValueError as exc:
        if str(exc) == "datasource_not_found":
            raise HTTPException(status_code=404, detail="datasource_not_found") from exc
        raise
    await session.commit()
    await session.refresh(row)
    return await _memory_document_response(session, row)


@router.patch(
    "/admin/datasources/{datasource_id}/memory-document",
    response_model=AdminDatasourceMemoryDocumentResponse,
)
async def update_admin_memory_document(
    datasource_id: str,
    body: AdminDatasourceMemoryDocumentUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceMemoryDocumentResponse:
    del datasource_id, body, session
    raise HTTPException(status_code=409, detail="memory_document_managed_by_agent")


@router.get(
    "/admin/qa-examples",
    response_model=AdminDatasourceQaExampleListResponse,
)
async def list_admin_qa_examples(
    datasource_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceQaExampleListResponse:
    stmt = select(DatasourceQaExample).order_by(
        DatasourceQaExample.updated_at.desc(),
        DatasourceQaExample.id.asc(),
    )
    if datasource_id:
        stmt = stmt.where(DatasourceQaExample.datasource_id == datasource_id.strip())
    rows = await session.execute(stmt)
    return AdminDatasourceQaExampleListResponse(items=[_qa_response(row) for row in rows.scalars().all()])


@router.get(
    "/admin/datasources/{datasource_id}/qa-examples",
    response_model=AdminDatasourceQaExampleListResponse,
)
async def list_admin_datasource_qa_examples(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceQaExampleListResponse:
    rows = await session.execute(
        select(DatasourceQaExample)
        .where(DatasourceQaExample.datasource_id == datasource_id)
        .order_by(DatasourceQaExample.updated_at.desc(), DatasourceQaExample.id.asc())
    )
    return AdminDatasourceQaExampleListResponse(items=[_qa_response(row) for row in rows.scalars().all()])


@router.get(
    "/admin/datasources/{datasource_id}/thread-summaries",
    response_model=AdminThreadSummaryListResponse,
)
async def list_admin_thread_summaries(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminThreadSummaryListResponse:
    rows = await session.execute(
        select(ThreadContextSummary)
        .where(ThreadContextSummary.datasource_id == datasource_id)
        .order_by(
            ThreadContextSummary.updated_at.desc(),
            ThreadContextSummary.thread_id.asc(),
        )
    )
    return AdminThreadSummaryListResponse(
        items=[_summary_response(row) for row in rows.scalars().all()]
    )
