"""Async SQLAlchemy engine and session factory with explicit pool limits."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db_url import normalize_async_database_url

__all__ = [
    "AsyncSessionLocal",
    "async_engine",
    "get_db",
    "normalize_async_database_url",
]

_settings = get_settings()
_async_url = normalize_async_database_url(_settings.sql_agent_database_url)

async_engine = create_async_engine(
    _async_url,
    pool_size=_settings.sql_agent_db_pool_size,
    max_overflow=_settings.sql_agent_db_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one `AsyncSession` per request."""
    async with AsyncSessionLocal() as session:
        yield session
