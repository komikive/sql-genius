# SQL Genius — Python backend

FastAPI service for the SQL Genius rewrite. Dependencies and lockfile are managed with [uv](https://github.com/astral-sh/uv).

## Prerequisites

- Python `>=3.12,<3.15` (see `pyproject.toml`)
- [uv](https://docs.astral.sh/uv/) installed

## Setup

From this directory:

```bash
uv sync
```

Installs runtime and dev dependencies from `uv.lock`. Use `uv sync --frozen` in CI when you need a strictly reproducible install.

## Configuration

Application settings load the repository-root `.env` and then the git-ignored `.env.local`; shell variables have highest priority. Put local secrets in `.env.local`, not the tracked `.env`. The typed `pydantic-settings` layer in `app/core/config.py` resolves these paths whether your current directory is the repo root or `backend/`.

## Run modes (host vs Docker Compose)

- **A — Host backend + Compose Postgres:** Start only the database from the repo root (`docker compose up postgres -d`). Use `SQL_AGENT_DATABASE_URL` with `127.0.0.1` as the DB host so `uv run` on your machine reaches the published port `5432`.
- **B — Full defense stack in Compose:** From the repo root, `./scripts/demo.sh up` (or `docker compose up -d --build`) runs Postgres, applies Alembic migrations during backend boot, starts the API on `8000`, and serves the React frontend on `3000` through the `web` container.

## Run the API (local)

From `backend/`:

```bash
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

This uses the app factory (`create_app`) so lifespan and wiring added in later plans stay centralized.

Equivalent without `--factory` (the module also exposes `app = create_app()`):

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Database migrations (Alembic)

Migrations run against the same URL as the app: `SQL_AGENT_DATABASE_URL` in the **repository root** `.env` (see Configuration). Use the `postgresql+psycopg://` scheme (plain `postgresql://` is normalized to that driver).

In the compose-managed launch path, the backend container now runs `alembic upgrade head` before starting `uvicorn`, so manual migration is not required for the defense stack.

For host-run development, with Postgres available (for example `docker compose up postgres -d` from the repo root), apply revisions manually:

```bash
cd backend
uv run alembic upgrade head
```

Inspect current revision:

```bash
uv run alembic current
```

## Runtime guards and Langfuse

Business-database queries are bounded by `SQL_AGENT_QUERY_MAX_ROWS` and a database-native `SQL_AGENT_QUERY_TIMEOUT_MS` for PostgreSQL/MySQL. Chat requests also reject a second active run for the same LangGraph thread inside one API process; multi-worker deployments should replace this process-local guard with Redis or a PostgreSQL advisory lock.

Langfuse is opt-in. In `.env.local`, set `SQL_AGENT_OBSERVABILITY_ENABLED=1` plus `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and optionally `LANGFUSE_BASE_URL`. Traces cover the request, LangGraph nodes, LLM generations, tools, SQL execution, and post-turn learning. Prompt, SQL, and result bodies stay out of traces unless `SQL_AGENT_OBSERVABILITY_CAPTURE_CONTENT=1`; common credentials are redacted when capture is enabled.

## Tests

Contract tests under `tests/api/` and `tests/config/` set `SQL_AGENT_SKIP_DB_LIFESPAN=1` so the lifespan **skips** the `SELECT 1` DB check; you still need a valid `SQL_AGENT_DATABASE_URL` string for SQLAlchemy engine construction. For integration runs against a real Postgres instance, omit the skip flag so startup verifies connectivity.

```bash
uv run pytest
```
