"""SAFE-02: settings load from env; chat vs embedding stay distinct; extras ignored."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, find_repo_root, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_database_url_and_models_under_controlled_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATABASE_URL",
        "postgresql+psycopg://user:pass@127.0.0.1:5999/testdb",
    )
    monkeypatch.setenv("SQL_AGENT_CHAT_MODEL", "test-chat-model")
    monkeypatch.setenv("SQL_AGENT_EMBEDDING_MODEL", "test-embedding-model")
    s = Settings()
    assert s.sql_agent_database_url.startswith("postgresql+psycopg://")
    assert s.sql_agent_chat_model == "test-chat-model"
    assert s.sql_agent_embedding_model == "test-embedding-model"
    assert s.sql_agent_chat_model != s.sql_agent_embedding_model


def test_unrelated_env_vars_do_not_break_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATABASE_URL",
        "postgresql+psycopg://user:pass@127.0.0.1:5999/testdb",
    )
    monkeypatch.setenv("SQL_AGENT_EXTRA_UNUSED_KEY_FOR_TESTS", "should-be-ignored")
    s = Settings()
    assert "should-be-ignored" not in s.model_dump_json()


def test_find_repo_root_falls_back_to_nearest_pyproject(tmp_path: Path) -> None:
    project_root = tmp_path / "backend"
    config_path = project_root / "app" / "core" / "config.py"

    config_path.parent.mkdir(parents=True)
    config_path.write_text("# test file\n")
    (project_root / "pyproject.toml").write_text("[project]\nname = 'demo'\nversion = '0.1.0'\n")

    assert find_repo_root(config_path) == project_root
