"""Contracts for execution helper routes."""

from __future__ import annotations

from app.api.routers import execution
from app.core.config import get_settings


def test_list_datasources_from_settings_json(client, monkeypatch) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATASOURCES_JSON",
        """[
          {
            "id": "default",
            "name": "Local Postgres Demo",
            "url": "postgresql+psycopg://demo:demo@localhost:5432/sql_agent"
          },
          {
            "id": "mysql-finance",
            "label": "Finance MySQL",
            "url": "mysql+pymysql://demo:demo@localhost:3306/finance"
          }
        ]""",
    )
    get_settings.cache_clear()

    try:
        response = client.get("/api/v1/execution/datasources")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    items_by_id = {item["id"]: item for item in body["items"]}
    assert items_by_id["default"] == {
        "id": "default",
        "label": "Local Postgres Demo",
        "dialect": "postgresql",
        "is_default": True,
    }
    assert items_by_id["mysql-finance"] == {
        "id": "mysql-finance",
        "label": "Finance MySQL",
        "dialect": "mysql",
        "is_default": False,
    }


def test_run_sql_rejects_unsafe_sql_with_readable_error(client) -> None:
    response = client.post(
        "/api/v1/execution/run",
        json={"datasource_id": "default", "sql": "DELETE FROM invoices"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unsafe_sql"
    assert "SELECT-only safety guard" in body["error"]["message"]
    assert body["error"]["details"]["reason"]


def test_run_sql_masks_execution_failure_details(client, monkeypatch) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATASOURCES_JSON",
        """[
          {
            "id": "default",
            "name": "Local Postgres Demo",
            "url": "postgresql+psycopg://demo:secret@localhost:5432/sql_agent"
          }
        ]""",
    )
    get_settings.cache_clear()

    def _broken_execution(*args, **kwargs):
        raise RuntimeError(
            "could not connect to postgresql+psycopg://demo:secret@localhost:5432/sql_agent"
        )

    monkeypatch.setattr(execution, "run_bounded_select", _broken_execution)

    try:
        response = client.post(
            "/api/v1/execution/run",
            json={"datasource_id": "default", "sql": "SELECT 1 AS one"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "execution_failed"
    assert "could not connect" in body["error"]["message"]
    assert "secret" not in body["error"]["message"]
    assert "***" in body["error"]["message"]
