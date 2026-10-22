"""Typed API response and error envelope models (SAFE-03)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """`GET /health` body — direct model (no wrapper) for Phase 1."""

    status: str = Field(..., description='Always "ok" when the service is up.')
    service: str = Field(..., description="Logical service name.")
    version: str = Field(..., description="Application semver.")


class ErrorBody(BaseModel):
    """Single error payload inside `ErrorEnvelope`."""

    code: str
    message: str
    details: Any | None = None


class ErrorEnvelope(BaseModel):
    """Consistent JSON shape for HTTP and validation failures."""

    error: ErrorBody

