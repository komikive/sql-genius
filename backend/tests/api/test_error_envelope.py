"""Contract: validation and HTTP errors use the same ErrorEnvelope (SAFE-03)."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app


def test_validation_error_returns_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/chat/stream", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert isinstance(body["error"]["details"], list)


def test_http_error_returns_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/definitely-not-a-route")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert isinstance(body["error"]["message"], str)


def test_unhandled_exception_returns_envelope() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_server_error"
    assert body["error"]["message"] == "Internal server error"


def test_structured_http_error_detail_is_preserved() -> None:
    app = create_app()

    @app.get("/structured-http")
    async def structured_http():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unsafe_sql",
                "message": "No mutation statements are allowed.",
                "details": {"reason": "mutation_detected"},
            },
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/structured-http")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unsafe_sql"
    assert body["error"]["message"] == "No mutation statements are allowed."
    assert body["error"]["details"] == {"reason": "mutation_detected"}
