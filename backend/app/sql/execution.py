"""Bounded read-only query execution shared by Agent tools and the API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


@dataclass(frozen=True)
class BoundedQueryResult:
    rows: list[dict[str, Any]]
    truncated: bool


def _apply_statement_timeout(connection: Any, timeout_ms: int) -> None:
    if timeout_ms <= 0:
        return
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
    elif dialect in {"mysql", "mariadb"}:
        connection.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")


def run_bounded_select(
    url: str,
    sql: str,
    *,
    max_rows: int,
    timeout_ms: int,
) -> BoundedQueryResult:
    """Execute one SELECT with a database timeout and bounded client fetch."""
    limit = max(1, int(max_rows))
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            _apply_statement_timeout(connection, int(timeout_ms))
            result = connection.execute(text(sql))
            fetched = result.mappings().fetchmany(limit + 1)
            return BoundedQueryResult(
                rows=[dict(row) for row in fetched[:limit]],
                truncated=len(fetched) > limit,
            )
    finally:
        engine.dispose()
