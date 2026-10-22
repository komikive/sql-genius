"""Datasource connectivity, schema introspection, and safe profiling helpers."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.core.db_url import normalize_database_driver_url

SCHEMA_TABLE_LIMIT = 200
PROFILE_TABLE_LIMIT = 48
PROFILE_SAMPLE_ROW_LIMIT = 5
PROFILE_QUERY_ROW_LIMIT = 50

_URL_SECRET_RE = re.compile(r"://([^:@/\s]+):([^@/\s]+)@")


def sanitize_error_message(exc: Exception) -> str:
    raw = _URL_SECRET_RE.sub(r"://\1:***@", str(exc))
    raw = raw.strip().replace("\n", " ")
    if "127.0.0.1" in raw and "Connection refused" in raw:
        return (
            "Connection refused at 127.0.0.1. If the API runs in Docker, use a "
            "container-reachable hostname such as `postgres` instead of localhost."
        )
    if not raw:
        return f"{type(exc).__name__}"
    if len(raw) > 240:
        raw = raw[:237] + "..."
    return raw


def run_connection_probe(connection_url: str) -> tuple[bool, str]:
    try:
        engine = create_engine(normalize_database_driver_url(connection_url), poolclass=NullPool)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "Connection successful"
    except Exception as exc:
        return False, sanitize_error_message(exc)


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (date, datetime, time)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return str(value)


def _quote_identifier(conn: Any, identifier: str) -> str:
    return conn.dialect.identifier_preparer.quote(identifier)


def _table_comment(inspector: Any, table_name: str) -> str | None:
    try:
        payload = inspector.get_table_comment(table_name) or {}
    except Exception:
        return None
    text_value = payload.get("text")
    if not isinstance(text_value, str):
        return None
    cleaned = text_value.strip()
    return cleaned or None


def _column_comment(column: dict[str, Any]) -> str | None:
    raw = column.get("comment")
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None


def introspect_schema_payload(connection_url: str, dialect: str) -> dict[str, Any]:
    engine = create_engine(normalize_database_driver_url(connection_url), poolclass=NullPool)
    with engine.connect() as conn:
        inspector = inspect(conn)
        table_names = sorted(inspector.get_table_names())
        limited_names = table_names[:SCHEMA_TABLE_LIMIT]
        tables: list[dict[str, Any]] = []
        column_count = 0
        for table_name in limited_names:
            columns = inspector.get_columns(table_name)
            column_count += len(columns)
            tables.append(
                {
                    "name": table_name,
                    "comment": _table_comment(inspector, table_name),
                    "columns": [
                        {
                            "name": column.get("name"),
                            "type": str(column.get("type")),
                            "nullable": bool(column.get("nullable", True)),
                            "comment": _column_comment(column),
                        }
                        for column in columns
                    ],
                }
            )

    return {
        "dialect": dialect,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "table_limit": SCHEMA_TABLE_LIMIT,
        "truncated": len(table_names) > SCHEMA_TABLE_LIMIT,
        "table_count": len(limited_names),
        "column_count": column_count,
        "tables": tables,
    }


def build_onboarding_profile_payload(connection_url: str, dialect: str) -> dict[str, Any]:
    engine = create_engine(normalize_database_driver_url(connection_url), poolclass=NullPool)
    with engine.connect() as conn:
        inspector = inspect(conn)
        table_names = sorted(inspector.get_table_names())
        limited_names = table_names[:PROFILE_TABLE_LIMIT]
        tables: list[dict[str, Any]] = []
        total_columns = 0
        for table_name in limited_names:
            columns = inspector.get_columns(table_name)
            total_columns += len(columns)
            quoted_table = _quote_identifier(conn, table_name)
            quoted_columns = ", ".join(
                _quote_identifier(conn, str(column.get("name"))) for column in columns
            )
            sample_rows: list[dict[str, Any]] = []
            sample_error: str | None = None
            if quoted_columns:
                try:
                    rows = conn.execute(
                        text(
                            f"SELECT {quoted_columns} FROM {quoted_table} LIMIT :limit"
                        ),
                        {"limit": PROFILE_SAMPLE_ROW_LIMIT},
                    ).mappings()
                    sample_rows = [
                        {str(key): _json_safe_value(value) for key, value in row.items()}
                        for row in rows
                    ]
                except Exception as exc:
                    sample_error = sanitize_error_message(exc)

            primary_key = inspector.get_pk_constraint(table_name) or {}
            foreign_keys = inspector.get_foreign_keys(table_name) or []
            tables.append(
                {
                    "name": table_name,
                    "comment": _table_comment(inspector, table_name),
                    "columns": [
                        {
                            "name": column.get("name"),
                            "type": str(column.get("type")),
                            "nullable": bool(column.get("nullable", True)),
                            "default": _json_safe_value(column.get("default")),
                            "comment": _column_comment(column),
                        }
                        for column in columns
                    ],
                    "primary_key": primary_key.get("constrained_columns") or [],
                    "foreign_keys": [
                        {
                            "constrained_columns": fk.get("constrained_columns") or [],
                            "referred_table": fk.get("referred_table"),
                            "referred_columns": fk.get("referred_columns") or [],
                        }
                        for fk in foreign_keys
                    ],
                    "sample_rows": sample_rows,
                    "sample_error": sample_error,
                }
            )

    return {
        "dialect": dialect,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "table_limit": PROFILE_TABLE_LIMIT,
        "sample_row_limit": PROFILE_SAMPLE_ROW_LIMIT,
        "table_count": len(limited_names),
        "column_count": total_columns,
        "truncated": len(table_names) > PROFILE_TABLE_LIMIT,
        "tables": tables,
    }
