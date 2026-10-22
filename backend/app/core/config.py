"""Settings: resolve REPO_ROOT from repo markers or a packaged backend project root."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.rag.constants import DEFAULT_EMBEDDING_DIMENSION


def find_repo_root(start_path: Path | None = None) -> Path:
    """Find the repo root, falling back to the nearest Python project root in packaged images."""
    origin = (start_path or Path(__file__).resolve()).resolve()
    current = origin if origin.is_dir() else origin.parent
    pyproject_fallback: Path | None = None

    for parent in [current, *current.parents]:
        env_example = parent / ".env.example"
        compose = parent / "docker-compose.yml"
        if env_example.is_file() or compose.is_file():
            return parent
        if pyproject_fallback is None and (parent / "pyproject.toml").is_file():
            pyproject_fallback = parent

    if pyproject_fallback is not None:
        return pyproject_fallback

    msg = (
        "repository root not found: no parent of app/core/config.py contains "
        "`.env.example`, `docker-compose.yml`, or `pyproject.toml`"
    )
    raise RuntimeError(msg)


REPO_ROOT: Path = find_repo_root()


class Settings(BaseSettings):
    """Application settings; shell env and ignored `.env.local` override root `.env`."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    sql_agent_database_url: str = Field(validation_alias="SQL_AGENT_DATABASE_URL")
    sql_agent_db_pool_size: int = Field(
        default=5,
        validation_alias="SQL_AGENT_DB_POOL_SIZE",
    )
    sql_agent_db_max_overflow: int = Field(
        default=10,
        validation_alias="SQL_AGENT_DB_MAX_OVERFLOW",
    )
    sql_agent_query_max_rows: int = Field(
        default=500,
        validation_alias="SQL_AGENT_QUERY_MAX_ROWS",
    )
    sql_agent_query_timeout_ms: int = Field(
        default=30_000,
        validation_alias="SQL_AGENT_QUERY_TIMEOUT_MS",
    )

    sql_agent_chat_base_url: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_CHAT_BASE_URL",
    )
    sql_agent_chat_api_key: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_CHAT_API_KEY",
    )
    sql_agent_chat_model: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_CHAT_MODEL",
    )

    sql_agent_embedding_base_url: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_EMBEDDING_BASE_URL",
    )
    sql_agent_embedding_api_key: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_EMBEDDING_API_KEY",
    )
    sql_agent_embedding_model: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_EMBEDDING_MODEL",
    )
    sql_agent_embedding_dimension: int = Field(
        default=DEFAULT_EMBEDDING_DIMENSION,
        validation_alias="SQL_AGENT_EMBEDDING_DIMENSION",
    )

    sql_agent_datasources_json: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_DATASOURCES_JSON",
    )

    sql_agent_runtime_memory_char_budget: int = Field(
        default=2200,
        validation_alias="SQL_AGENT_RUNTIME_MEMORY_CHAR_BUDGET",
    )
    sql_agent_datasource_memory_char_budget: int = Field(
        default=3000,
        validation_alias="SQL_AGENT_DATASOURCE_MEMORY_CHAR_BUDGET",
    )
    sql_agent_memory_auto_activate_threshold: float = Field(
        default=0.82,
        validation_alias="SQL_AGENT_MEMORY_AUTO_ACTIVATE_THRESHOLD",
    )
    sql_agent_thread_context_char_budget: int = Field(
        default=7000,
        validation_alias="SQL_AGENT_THREAD_CONTEXT_CHAR_BUDGET",
    )
    sql_agent_thread_summary_char_budget: int = Field(
        default=2200,
        validation_alias="SQL_AGENT_THREAD_SUMMARY_CHAR_BUDGET",
    )
    sql_agent_thread_context_tail_turns: int = Field(
        default=6,
        validation_alias="SQL_AGENT_THREAD_CONTEXT_TAIL_TURNS",
    )
    sql_agent_thread_context_compression_min_turns: int = Field(
        default=8,
        validation_alias="SQL_AGENT_THREAD_CONTEXT_COMPRESSION_MIN_TURNS",
    )
    sql_agent_autonomous_max_steps: int = Field(
        default=15,
        validation_alias="SQL_AGENT_AUTONOMOUS_MAX_STEPS",
    )
    sql_agent_prompt_timezone: str = Field(
        default="Asia/Shanghai",
        validation_alias="SQL_AGENT_PROMPT_TIMEZONE",
    )

    sql_agent_suggestion_model: str | None = Field(
        default=None,
        validation_alias="SQL_AGENT_SUGGESTION_MODEL",
    )

    sql_agent_env: str = Field(
        default="dev",
        validation_alias="SQL_AGENT_ENV",
    )
    sql_agent_observability_enabled: bool = Field(
        default=False,
        validation_alias="SQL_AGENT_OBSERVABILITY_ENABLED",
    )
    sql_agent_observability_capture_content: bool = Field(
        default=False,
        validation_alias="SQL_AGENT_OBSERVABILITY_CAPTURE_CONTENT",
    )
    sql_agent_observability_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        validation_alias="SQL_AGENT_OBSERVABILITY_SAMPLE_RATE",
    )
    langfuse_public_key: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_PUBLIC_KEY",
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        validation_alias="LANGFUSE_SECRET_KEY",
    )
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias="LANGFUSE_BASE_URL",
    )
    sql_agent_skip_db_lifespan: bool = Field(
        default=False,
        validation_alias="SQL_AGENT_SKIP_DB_LIFESPAN",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Lazy singleton for settings (instantiates on first use, not at import)."""
    return Settings()
