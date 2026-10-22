"""Contracts for admin session and SQL execution history."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.api.routers import execution
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.admin_session import AdminSession
from app.db.models.sql_execution_history import SqlExecutionHistory
from app.sql.execution import BoundedQueryResult


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    AdminSession.__table__,
                    SqlExecutionHistory.__table__,
                ],
            )
        )
        await conn.execute(
            sa.text("DELETE FROM sql_execution_history WHERE thread_id LIKE 'test-%'")
        )
        await conn.execute(sa.text("DELETE FROM admin_sessions WHERE thread_id LIKE 'test-%'"))


async def _get_session_row(thread_id: str) -> AdminSession | None:
    async with AsyncSessionLocal() as session:
        return await session.get(AdminSession, thread_id)


async def _get_latest_execution(thread_id: str) -> SqlExecutionHistory | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.select(SqlExecutionHistory)
            .where(SqlExecutionHistory.thread_id == thread_id)
            .order_by(SqlExecutionHistory.id.desc())
            .limit(1)
        )
        return result.scalars().first()


@pytest.fixture(autouse=True)
def clean_history_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


def test_chat_stream_registers_admin_session(client) -> None:
    thread_id = "test-session-history"
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={
            "thread_id": thread_id,
            "message": "What was the total invoice amount per region last quarter for finance?",
            "resume": False,
        },
    ) as response:
        body = response.read().decode()

    assert "event: done" in body
    row = anyio.run(_get_session_row, thread_id)
    assert row is not None
    assert row.turn_count == 1
    assert "finance" in (row.last_user_message or "").lower()

    listing = client.get("/api/v1/admin/history/sessions")
    assert listing.status_code == 200, listing.text
    assert any(item["thread_id"] == thread_id for item in listing.json()["items"])


def test_execution_run_records_success_and_lists_in_admin_history(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATASOURCES_JSON",
        """[
          {
            "id": "default",
            "name": "Local Postgres Demo",
            "url": "postgresql+psycopg://demo:secret@localhost:5432/sql_agent"
          }
        ]""",
    )
    get_settings.cache_clear()

    monkeypatch.setattr(
        execution,
        "run_bounded_select",
        lambda *args, **kwargs: BoundedQueryResult(rows=[{"ok": 1}], truncated=False),
    )

    try:
        response = client.post(
            "/api/v1/execution/run",
            json={
                "thread_id": "test-history-success",
                "datasource_id": "default",
                "sql": "SELECT 1 AS ok",
            },
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200, response.text
    history_row = anyio.run(_get_latest_execution, "test-history-success")
    assert history_row is not None
    assert history_row.status == "success"
    assert history_row.rowcount == 1

    listing = client.get("/api/v1/admin/history/executions")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert any(item["thread_id"] == "test-history-success" for item in items)

    execution_id = next(item["id"] for item in items if item["thread_id"] == "test-history-success")
    detail = client.get(f"/api/v1/admin/history/executions/{execution_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["sql_text"] == "SELECT 1 AS ok"


def test_execution_run_records_failed_history(client, monkeypatch) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATASOURCES_JSON",
        """[
          {
            "id": "default",
            "name": "Local Postgres Demo",
            "url": "postgresql+psycopg://demo:secret@localhost:5432/sql_agent"
          }
        ]""",
    )
    get_settings.cache_clear()

    def _broken_execution(*args, **kwargs):
        raise RuntimeError(
            "could not connect to postgresql+psycopg://demo:secret@localhost:5432/sql_agent"
        )

    monkeypatch.setattr(execution, "run_bounded_select", _broken_execution)

    try:
        response = client.post(
            "/api/v1/execution/run",
            json={
                "thread_id": "test-history-failed",
                "datasource_id": "default",
                "sql": "SELECT 1 AS ok",
            },
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 502, response.text
    history_row = anyio.run(_get_latest_execution, "test-history-failed")
    assert history_row is not None
    assert history_row.status == "failed"
    assert "secret" not in (history_row.error_message or "")
    assert "***" in (history_row.error_message or "")

