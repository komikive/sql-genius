"""Pytest fixtures: env must be set before importing `app` or `app.core.db`."""

from __future__ import annotations

import os

# Integration-style URL; engine is not pinged when SQL_AGENT_SKIP_DB_LIFESPAN=1 (pytest default).
os.environ.setdefault(
    "SQL_AGENT_DATABASE_URL",
    "postgresql+psycopg://sql_agent:sql_agent@127.0.0.1:5432/sql_agent"
)
os.environ.setdefault("SQL_AGENT_SKIP_DB_LIFESPAN", "1")
# Prevent real chat/embedding calls during pytest (local `.env` may contain provider keys).
os.environ.setdefault("SQL_AGENT_CHAT_API_KEY", "")
os.environ.setdefault("SQL_AGENT_CHAT_BASE_URL", "")
os.environ.setdefault("SQL_AGENT_CHAT_MODEL", "")
os.environ.setdefault("SQL_AGENT_EMBEDDING_API_KEY", "")
os.environ.setdefault("SQL_AGENT_EMBEDDING_BASE_URL", "")
os.environ.setdefault("SQL_AGENT_EMBEDDING_MODEL", "")
os.environ.setdefault("SQL_AGENT_OBSERVABILITY_ENABLED", "0")

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c
