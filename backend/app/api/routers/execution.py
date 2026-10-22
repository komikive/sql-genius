"""Execute read-only SELECT queries against configured business datasources (Phase 4)."""

from __future__ import annotations

import anyio
import re
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.observability import trace_content, trace_observation
from app.services.datasource_resolve import (
    list_resolved_datasources,
    resolve_datasource_url,
)
from app.services.history_audit import record_sql_execution
from app.sql.execution import run_bounded_select
from app.sql.safety import SqlSafetyService

router = APIRouter()
_URL_SECRET_RE = re.compile(r"://([^:@/\s]+):([^@/\s]+)@")


class ExecuteRequest(BaseModel):
    datasource_id: str = Field(..., min_length=1)
    sql: str = Field(..., min_length=1)
    thread_id: str | None = None


class ExecuteResponse(BaseModel):
    rows: list[dict]
    rowcount: int
    truncated: bool = False


class DatasourceOption(BaseModel):
    id: str
    label: str
    dialect: str | None = None
    is_default: bool = False


class DatasourceListResponse(BaseModel):
    items: list[DatasourceOption]


def _safe_execution_message(exc: Exception) -> str:
    raw = _URL_SECRET_RE.sub(r"://\1:***@", str(exc)).strip().replace("\n", " ")
    if "127.0.0.1" in raw and "Connection refused" in raw:
        return (
            "Datasource connection failed at 127.0.0.1. If the API runs in Docker, "
            "use a container-reachable hostname such as `postgres` instead of localhost."
        )
    if not raw:
        return type(exc).__name__
    if len(raw) > 240:
        return raw[:237] + "..."
    return raw


def _http_error_message(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message:
            return message
        reason = detail.get("reason")
        if isinstance(reason, str) and reason:
            return reason
    return "Execution failed"


async def _try_record_execution(
    session: AsyncSession,
    *,
    thread_id: str | None,
    datasource_id: str | None,
    sql: str,
    status: str,
    rowcount: int | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    try:
        await record_sql_execution(
            session,
            thread_id=thread_id,
            datasource_id=datasource_id,
            sql_text=sql,
            status=status,
            rowcount=rowcount,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        return


async def _get_thread_bound_datasource(
    session: AsyncSession,
    thread_id: str | None,
) -> str | None:
    if not thread_id:
        return None
    result = await session.execute(
        text(
            """
            SELECT datasource_id
            FROM thread_conversation_turns
            WHERE thread_id = :thread_id
            ORDER BY id ASC
            LIMIT 1
            """
        ),
        {"thread_id": thread_id},
    )
    row = result.first()
    if row is None:
        return None
    return row[0]


@router.get("/execution/datasources", response_model=DatasourceListResponse)
async def list_datasources(
    session: AsyncSession = Depends(get_db),
) -> DatasourceListResponse:
    settings = get_settings()
    resolved = await list_resolved_datasources(session, settings)
    items = [
        DatasourceOption(
            id=item.id,
            label=item.label,
            dialect=item.dialect,
            is_default=item.is_default,
        )
        for item in resolved
    ]
    return DatasourceListResponse(items=items)


@router.post("/execution/run", response_model=ExecuteResponse)
async def run_sql(
    body: ExecuteRequest,
    session: AsyncSession = Depends(get_db),
) -> ExecuteResponse:
    """Workbench「执行 SQL」按钮入口：与 Agent execute_query 共用 SqlSafetyService。

    线程已绑定数据源时拒绝跨库执行（与 chat 线程约束一致）。
    """
    settings = get_settings()
    started_at = perf_counter()

    # 与 chat 一致：同 thread_id 只能查首次提问绑定的 datasource
    bound_datasource_id = await _get_thread_bound_datasource(session, body.thread_id)
    if bound_datasource_id is not None and bound_datasource_id != body.datasource_id:
        message = "This thread is already bound to another datasource and cannot execute SQL against a different datasource."
        await _try_record_execution(
            session,
            thread_id=body.thread_id,
            datasource_id=body.datasource_id,
            sql=body.sql,
            status="failed",
            error_message=message,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "thread_datasource_mismatch",
                "message": message,
                "details": {
                    "thread_id": body.thread_id,
                    "bound_datasource_id": bound_datasource_id,
                    "requested_datasource_id": body.datasource_id,
                },
            },
        )

    ok, reason = SqlSafetyService.validate(body.sql)
    if not ok:
        message = f"SQL rejected by the SELECT-only safety guard: {reason}"
        await _try_record_execution(
            session,
            thread_id=body.thread_id,
            datasource_id=body.datasource_id,
            sql=body.sql,
            status="failed",
            error_message=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unsafe_sql",
                "message": message,
                "details": {"reason": reason},
            },
        )
    try:
        url = await resolve_datasource_url(session, settings, body.datasource_id)
    except HTTPException as exc:
        await _try_record_execution(
            session,
            thread_id=body.thread_id,
            datasource_id=body.datasource_id,
            sql=body.sql,
            status="failed",
            error_message=_http_error_message(exc.detail),
        )
        raise

    def _run():
        return run_bounded_select(
            url,
            body.sql,
            max_rows=settings.sql_agent_query_max_rows,
            timeout_ms=settings.sql_agent_query_timeout_ms,
        )

    try:
        with trace_observation(
            "execute-sql-query",
            as_type="tool",
            input={"sql": body.sql},
            input_summary={"sql_chars": len(body.sql)},
            metadata={
                "datasource_id": body.datasource_id,
                "thread_id": body.thread_id,
                "max_rows": settings.sql_agent_query_max_rows,
                "timeout_ms": settings.sql_agent_query_timeout_ms,
            },
        ) as sql_span:
            query_result = await anyio.to_thread.run_sync(_run)
            if sql_span is not None:
                sql_span.update(
                    output=trace_content(
                        query_result.rows,
                        fallback={
                            "rowcount": len(query_result.rows),
                            "truncated": query_result.truncated,
                        },
                    )
                )
    except Exception as exc:
        message = _safe_execution_message(exc)
        await _try_record_execution(
            session,
            thread_id=body.thread_id,
            datasource_id=body.datasource_id,
            sql=body.sql,
            status="failed",
            error_message=message,
            duration_ms=int((perf_counter() - started_at) * 1000),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "execution_failed",
                "message": message,
            },
        ) from exc
    rows = query_result.rows
    await _try_record_execution(
        session,
        thread_id=body.thread_id,
        datasource_id=body.datasource_id,
        sql=body.sql,
        status="success",
        rowcount=len(rows),
        duration_ms=int((perf_counter() - started_at) * 1000),
    )
    return ExecuteResponse(
        rows=rows,
        rowcount=len(rows),
        truncated=query_result.truncated,
    )
