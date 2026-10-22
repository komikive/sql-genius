"""Admin session and SQL execution history browsing."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.db.models.admin_session import AdminSession
from app.db.models.sql_execution_history import SqlExecutionHistory

router = APIRouter()


class AdminSessionSummary(BaseModel):
    thread_id: str
    first_user_message: str | None = None
    last_user_message: str | None = None
    turn_count: int
    created_at: datetime | None = None
    last_activity_at: datetime | None = None


class AdminSessionListResponse(BaseModel):
    items: list[AdminSessionSummary]
    limit: int
    offset: int


class AdminExecutionSummary(BaseModel):
    id: int
    thread_id: str | None = None
    datasource_id: str | None = None
    status: str
    rowcount: int | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    sql_excerpt: str
    executed_at: datetime | None = None


class AdminExecutionDetail(AdminExecutionSummary):
    sql_text: str


class AdminExecutionListResponse(BaseModel):
    items: list[AdminExecutionSummary]
    limit: int
    offset: int


def _sql_excerpt(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _serialize_execution(row: SqlExecutionHistory) -> AdminExecutionDetail:
    return AdminExecutionDetail(
        id=row.id,
        thread_id=row.thread_id,
        datasource_id=row.datasource_id,
        status=row.status,
        rowcount=row.rowcount,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
        sql_excerpt=_sql_excerpt(row.sql_text),
        executed_at=row.executed_at,
        sql_text=row.sql_text,
    )


@router.get("/admin/history/sessions", response_model=AdminSessionListResponse)
async def list_admin_sessions(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> AdminSessionListResponse:
    result = await session.execute(
        select(AdminSession)
        .order_by(AdminSession.last_activity_at.desc(), AdminSession.thread_id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AdminSessionListResponse(
        items=[
            AdminSessionSummary(
                thread_id=row.thread_id,
                first_user_message=row.first_user_message,
                last_user_message=row.last_user_message,
                turn_count=row.turn_count,
                created_at=row.created_at,
                last_activity_at=row.last_activity_at,
            )
            for row in result.scalars().all()
        ],
        limit=limit,
        offset=offset,
    )


@router.delete("/admin/history/sessions/{thread_id}", status_code=204)
async def delete_admin_session(
    thread_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    row = await session.get(AdminSession, thread_id)
    if row is None:
        raise HTTPException(status_code=404, detail="admin_session_not_found")

    await session.execute(text("DELETE FROM sql_execution_history WHERE thread_id = :thread_id"), {"thread_id": thread_id})
    await session.execute(text("DELETE FROM learning_signals WHERE thread_id = :thread_id"), {"thread_id": thread_id})
    await session.execute(text("DELETE FROM thread_conversation_turns WHERE thread_id = :thread_id"), {"thread_id": thread_id})
    await session.execute(text("DELETE FROM thread_context_summaries WHERE thread_id = :thread_id"), {"thread_id": thread_id})
    await session.execute(delete(AdminSession).where(AdminSession.thread_id == thread_id))
    await session.commit()
    return Response(status_code=204)


@router.get("/admin/history/executions", response_model=AdminExecutionListResponse)
async def list_admin_executions(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    thread_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> AdminExecutionListResponse:
    query = select(SqlExecutionHistory)
    if status:
        query = query.where(SqlExecutionHistory.status == status)
    if thread_id:
        query = query.where(SqlExecutionHistory.thread_id == thread_id)
    query = query.order_by(SqlExecutionHistory.executed_at.desc(), SqlExecutionHistory.id.desc())
    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    return AdminExecutionListResponse(
        items=[
            AdminExecutionSummary(
                id=row.id,
                thread_id=row.thread_id,
                datasource_id=row.datasource_id,
                status=row.status,
                rowcount=row.rowcount,
                error_message=row.error_message,
                duration_ms=row.duration_ms,
                sql_excerpt=_sql_excerpt(row.sql_text),
                executed_at=row.executed_at,
            )
            for row in result.scalars().all()
        ],
        limit=limit,
        offset=offset,
    )


@router.get("/admin/history/executions/{execution_id}", response_model=AdminExecutionDetail)
async def get_admin_execution(
    execution_id: int,
    session: AsyncSession = Depends(get_db),
) -> AdminExecutionDetail:
    row = await session.get(SqlExecutionHistory, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="execution_history_not_found")
    return _serialize_execution(row)
