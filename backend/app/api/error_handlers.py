"""Global exception handlers — one typed error envelope (SAFE-03)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.response_models import ErrorBody, ErrorEnvelope

logger = logging.getLogger(__name__)


def _error_json(status_code: int, envelope: ErrorEnvelope) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(),
    )


def _http_error_body(detail: Any) -> ErrorBody:
    if isinstance(detail, str):
        return ErrorBody(code="http_error", message=detail, details=None)

    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        reason = detail.get("reason")
        details = detail.get("details")

        if not isinstance(code, str) or not code:
            code = "http_error"
        if not isinstance(message, str) or not message:
            if isinstance(reason, str) and reason:
                message = reason
            else:
                message = "HTTP error"
        if details is None:
            extra = {
                key: value
                for key, value in detail.items()
                if key not in {"code", "message", "details"}
            }
            details = extra or None
        return ErrorBody(code=code, message=message, details=details)

    return ErrorBody(code="http_error", message="HTTP error", details=None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=_http_error_body(exc.detail),
        )
        if not isinstance(exc.detail, str):
            logger.debug("HTTPException non-str detail (sanitized for client)", exc_info=False)
        return _error_json(exc.status_code, envelope)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code="validation_error",
                message="Request validation failed",
                details=exc.errors(),
            ),
        )
        return _error_json(422, envelope)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled application exception", exc_info=exc)
        envelope = ErrorEnvelope(
            error=ErrorBody(
                code="internal_server_error",
                message="Internal server error",
                details=None,
            ),
        )
        return _error_json(500, envelope)
