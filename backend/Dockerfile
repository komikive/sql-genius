# FastAPI backend image: uv sync + uvicorn (D-20). Used by root docker-compose for acceptance/demo.
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "uv>=0.5.0"

WORKDIR /app

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY provision_complex_postgres_labs.py ./provision_complex_postgres_labs.py
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh \
    && uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Apply migrations before boot so `docker compose up` is a closer match to the defense launch contract.
CMD ["./docker-entrypoint.sh"]
