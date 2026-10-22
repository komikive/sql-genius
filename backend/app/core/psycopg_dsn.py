"""Convert SQLAlchemy-style async URLs to raw psycopg connection strings."""

from __future__ import annotations

from app.core.db_url import normalize_async_database_url


def raw_psycopg_dsn(async_database_url: str) -> str:
    """Strip SQLAlchemy driver prefix so psycopg `AsyncConnection.connect` accepts the URL."""
    normalized = normalize_async_database_url(async_database_url)
    if normalized.startswith("postgresql+psycopg://"):
        return "postgresql://" + normalized.removeprefix("postgresql+psycopg://")
    return normalized
