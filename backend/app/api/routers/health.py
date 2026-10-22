"""Health probe (meta)."""

from __future__ import annotations

import importlib.metadata

from fastapi import APIRouter

from app.api.response_models import HealthResponse

router = APIRouter()


def _app_version() -> str:
    try:
        return importlib.metadata.version("sql-agent-plus-backend")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["meta"],
    summary="Liveness / readiness probe",
)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="sql-genius",
        version=_app_version(),
    )
