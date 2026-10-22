"""Normalize database URLs for installed SQLAlchemy drivers (no engine side effects)."""

from __future__ import annotations


def normalize_database_driver_url(url: str) -> str:
    """Map shorthand database URLs to the drivers this project actually installs."""
    normalized = (url or "").strip()
    if normalized.startswith("postgresql+psycopg://"):
        return normalized
    if normalized.startswith("postgresql://"):
        return "postgresql+psycopg://" + normalized.removeprefix("postgresql://")
    if normalized.startswith("postgres://"):
        return "postgresql+psycopg://" + normalized.removeprefix("postgres://")
    if normalized.startswith("mysql+pymysql://"):
        return normalized
    if normalized.startswith("mysql://"):
        return "mysql+pymysql://" + normalized.removeprefix("mysql://")
    return normalized

def normalize_async_database_url(url: str) -> str:
    """Keep the async database entrypoint aligned with the shared driver normalization."""
    return normalize_database_driver_url(url)
