"""Admin-visible session and execution audit helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_session import AdminSession
from app.db.models.sql_execution_history import SqlExecutionHistory

__all__ = ["record_sql_execution", "touch_admin_session"]


def _excerpt(text: str | None, limit: int = 240) -> str | None:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


async def touch_admin_session(
    session: AsyncSession,
    *,
    thread_id: str,
    user_message: str | None,
    increment_turn: bool = True,
) -> None:
    """Create or update the lightweight admin session registry."""

    now = datetime.now(timezone.utc)
    message_excerpt = _excerpt(user_message)
    row = await session.get(AdminSession, thread_id)
    if row is None:
        row = AdminSession(
            thread_id=thread_id,
            first_user_message=message_excerpt,
            last_user_message=message_excerpt,
            turn_count=1 if increment_turn else 0,
            last_activity_at=now,
        )
        session.add(row)
        return

    if message_excerpt:
        if not row.first_user_message:
            row.first_user_message = message_excerpt
        row.last_user_message = message_excerpt
    if increment_turn:
        row.turn_count += 1
    row.last_activity_at = now


async def record_sql_execution(
    session: AsyncSession,
    *,
    thread_id: str | None,
    datasource_id: str | None,
    sql_text: str,
    status: str,
    rowcount: int | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Append one execution audit row for admin history browsing."""

    session.add(
        SqlExecutionHistory(
            thread_id=_excerpt(thread_id, limit=128),
            datasource_id=_excerpt(datasource_id, limit=128),
            sql_text=sql_text.strip(),
            status=status,
            rowcount=rowcount,
            error_message=_excerpt(error_message, limit=500),
            duration_ms=duration_ms,
        )
    )
