#!/bin/sh
set -eu

echo "Applying Alembic migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
