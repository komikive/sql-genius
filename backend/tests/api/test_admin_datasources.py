"""Contracts for datasource admin routes (Phase 6 first slice)."""

from __future__ import annotations

from collections.abc import Iterator

import anyio
import pytest
import sqlalchemy as sa

from app.api.routers import admin_datasources
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal, async_engine
from app.db.base import Base
from app.db.models.datasource import Datasource
from app.db.models.onboarding_run import OnboardingRun
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.skill_document import SkillDocument
from app.db.models.skill_pack import SkillPack
from app.services import onboarding_agent


async def _prepare_tables() -> None:
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Datasource.__table__,
                    DatasourceProfile.__table__,
                    DatasourceSchemaSnapshot.__table__,
                    OnboardingRun.__table__,
                    SkillPack.__table__,
                    SkillDocument.__table__,
                ],
            )
        )
        await conn.execute(sa.text("DELETE FROM skill_documents"))
        await conn.execute(sa.text("DELETE FROM skill_packs WHERE datasource_id LIKE 'test-%'"))
        await conn.execute(sa.text("DELETE FROM datasource_profiles WHERE datasource_id LIKE 'test-%'"))
        await conn.execute(
            sa.text("DELETE FROM datasource_schema_snapshots WHERE datasource_id LIKE 'test-%'")
        )
        await conn.execute(sa.text("DELETE FROM onboarding_runs"))
        await conn.execute(sa.text("DELETE FROM datasources WHERE id LIKE 'test-%'"))


@pytest.fixture(autouse=True)
def clean_datasource_tables() -> Iterator[None]:
    anyio.run(_prepare_tables)
    try:
        yield
    finally:
        anyio.run(_prepare_tables)


def _sample_onboarding_inputs() -> tuple[dict[str, object], dict[str, object]]:
    schema_payload = {
        "dialect": "postgresql",
        "captured_at": "2026-04-08T01:00:00+00:00",
        "table_limit": 200,
        "truncated": False,
        "table_count": 2,
        "column_count": 5,
        "tables": [
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False},
                    {"name": "customer_id", "type": "INTEGER", "nullable": False},
                ],
            },
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False},
                    {"name": "name", "type": "VARCHAR", "nullable": False},
                    {"name": "segment", "type": "VARCHAR", "nullable": True},
                ],
            },
        ],
    }
    onboarding_profile = {
        "dialect": "postgresql",
        "captured_at": "2026-04-08T01:00:00+00:00",
        "table_limit": 48,
        "sample_row_limit": 5,
        "truncated": False,
        "table_count": 2,
        "column_count": 5,
        "tables": [
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
                    {"name": "customer_id", "type": "INTEGER", "nullable": False, "default": None},
                ],
                "primary_key": ["id"],
                "foreign_keys": [
                    {
                        "constrained_columns": ["customer_id"],
                        "referred_table": "customers",
                        "referred_columns": ["id"],
                    }
                ],
                "sample_rows": [{"id": 1, "customer_id": 10}],
                "sample_error": None,
            },
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
                    {"name": "name", "type": "VARCHAR", "nullable": False, "default": None},
                    {"name": "segment", "type": "VARCHAR", "nullable": True, "default": None},
                ],
                "primary_key": ["id"],
                "foreign_keys": [],
                "sample_rows": [{"id": 10, "name": "Acme", "segment": "Enterprise"}],
                "sample_error": None,
            },
        ],
    }
    return schema_payload, onboarding_profile


def test_admin_datasource_crud_and_execution_catalog_merge(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SQL_AGENT_DATASOURCES_JSON",
        """[
          {
            "id": "test-default",
            "name": "Env Postgres",
            "url": "postgresql://env:secret@localhost:5432/envdb"
          },
          {
            "id": "env-only",
            "name": "Env Only",
            "url": "mysql://env:secret@localhost:3306/env_only"
          }
        ]""",
    )
    get_settings.cache_clear()

    try:
        created = client.post(
            "/api/v1/admin/datasources",
            json={
                "id": "test-default",
                "display_name": "DB Managed Default",
                "dialect": "postgresql",
                "connection_url": "postgresql://db:secret@localhost:5432/db",
                "is_default": True,
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["id"] == "test-default"
        assert body["display_name"] == "DB Managed Default"
        assert body["connection_url_masked"].endswith("@localhost:5432/db")

        admin_list = client.get("/api/v1/admin/datasources")
        assert admin_list.status_code == 200, admin_list.text
        assert admin_list.json()["items"][0]["display_name"] == "DB Managed Default"

        execution_list = client.get("/api/v1/execution/datasources")
        assert execution_list.status_code == 200, execution_list.text
        items_by_id = {item["id"]: item for item in execution_list.json()["items"]}
        assert items_by_id["test-default"] == {
            "id": "test-default",
            "label": "DB Managed Default",
            "dialect": "postgresql",
            "is_default": True,
        }
        assert items_by_id["env-only"] == {
            "id": "env-only",
            "label": "Env Only",
            "dialect": "mysql",
            "is_default": False,
        }
    finally:
        get_settings.cache_clear()


def test_admin_datasource_test_endpoint_uses_saved_id(
    client,
    monkeypatch,
) -> None:
    created = client.post(
        "/api/v1/admin/datasources",
        json={
            "id": "test-finance-db",
            "display_name": "Finance DB",
            "dialect": "postgresql",
            "connection_url": "postgresql://demo:secret@localhost:5432/finance",
        },
    )
    assert created.status_code == 201, created.text

    monkeypatch.setattr(
        admin_datasources,
        "_run_connection_probe",
        lambda connection_url: (
            True,
            "probe ok"
            if connection_url == "postgresql+psycopg://demo:secret@localhost:5432/finance"
            else "unexpected datasource",
        ),
    )

    response = client.post(
        "/api/v1/admin/datasources/test",
        json={"id": "test-finance-db"},
    )

    assert response.status_code == 200, response.text


def test_onboarding_analysis_output_normalizes_llm_shape_drift() -> None:
    output = onboarding_agent.OnboardingAnalysisOutput.model_validate(
        {
            "datasource_summary": {
                "name": "零售分析库",
                "description": "订单、会员、库存分析",
            },
            "candidate_skill_packs": [
                {
                    "name": "销售分析",
                    "summary": {"description": "关注 GMV、订单量与客单价"},
                    "metrics": ["总销售额", "订单量"],
                    "entities": ["订单", "会员"],
                    "business_rules": ["退款订单不计入销售额"],
                    "seed_documents": ["销售分析关注订单成交与退款口径。"],
                    "open_questions": ["GMV 是否包含运费"],
                }
            ],
            "unresolved_questions": {
                "question": "库存口径是否按可售库存计算",
                "input_kind": "single_select",
                "options": ["是", "否"],
            },
        }
    )

    assert output.datasource_summary == "订单、会员、库存分析"
    assert output.candidate_skill_packs[0].metrics == [{"name": "总销售额"}, {"name": "订单量"}]
    assert output.candidate_skill_packs[0].entities == [{"name": "订单"}, {"name": "会员"}]
    assert output.candidate_skill_packs[0].business_rules == [{"rule": "退款订单不计入销售额"}]
    assert output.candidate_skill_packs[0].seed_documents[0].content == "销售分析关注订单成交与退款口径。"
    assert output.candidate_skill_packs[0].open_questions[0].question == "GMV 是否包含运费"
    assert output.unresolved_questions[0].question == "库存口径是否按可售库存计算"


def test_admin_datasource_test_endpoint_normalizes_direct_url(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        admin_datasources,
        "_run_connection_probe",
        lambda connection_url: (
            True,
            "probe ok"
            if connection_url == "mysql+pymysql://demo:secret@localhost:3306/finance"
            else "unexpected datasource",
        ),
    )

    response = client.post(
        "/api/v1/admin/datasources/test",
        json={
            "connection_url": "mysql://demo:secret@localhost:3306/finance",
            "dialect": "mysql",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "message": "probe ok"}

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "message": "probe ok"}


def test_admin_introspection_persists_and_reads_schema(
    client,
    monkeypatch,
) -> None:
    created = client.post(
        "/api/v1/admin/datasources",
        json={
            "id": "test-finance-db",
            "display_name": "Finance DB",
            "dialect": "postgresql",
            "connection_url": "postgresql+psycopg://demo:secret@localhost:5432/finance",
        },
    )
    assert created.status_code == 201, created.text

    payload = {
        "dialect": "postgresql",
        "captured_at": "2026-04-08T01:00:00+00:00",
        "table_limit": 200,
        "truncated": False,
        "table_count": 1,
        "column_count": 2,
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False},
                    {"name": "name", "type": "VARCHAR", "nullable": False},
                ],
            }
        ],
    }
    monkeypatch.setattr(
        admin_datasources,
        "_introspect_schema_payload",
        lambda connection_url, dialect: payload,
    )

    introspect = client.post("/api/v1/admin/datasources/test-finance-db/introspect")
    assert introspect.status_code == 200, introspect.text
    intro_body = introspect.json()
    assert intro_body["ok"] is True
    assert intro_body["table_count"] == 1
    assert intro_body["column_count"] == 2

    schema = client.get("/api/v1/admin/datasources/test-finance-db/schema")
    assert schema.status_code == 200, schema.text
    assert schema.json() == payload

    detail = client.get("/api/v1/admin/datasources/test-finance-db")
    assert detail.status_code == 200, detail.text
    assert detail.json()["schema_available"] is True


def test_admin_onboarding_route_returns_background_run(
    client,
    monkeypatch,
) -> None:
    created = client.post(
        "/api/v1/admin/datasources",
        json={
            "id": "test-onboarding-db",
            "display_name": "Sales Warehouse",
            "dialect": "postgresql",
            "connection_url": "postgresql+psycopg://demo:secret@localhost:5432/sales",
        },
    )
    assert created.status_code == 201, created.text

    async def _fake_start_onboarding_run(session, datasource_id, _settings):
        run = OnboardingRun(
            datasource_id=datasource_id,
            status="running",
            phase="llm_analysis",
            status_message="正在调用模型分析数据源。",
            events=[
                {
                    "timestamp": "2026-04-11T03:00:00+00:00",
                    "phase": "prepare_schema_snapshot",
                    "message": "正在重新采集结构快照。",
                    "level": "info",
                }
            ],
            result_payload={},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run

    monkeypatch.setattr(admin_datasources, "start_onboarding_run", _fake_start_onboarding_run)

    response = client.post("/api/v1/admin/datasources/test-onboarding-db/onboarding/run")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["datasource_id"] == "test-onboarding-db"
    assert body["status"] == "running"
    assert body["phase"] == "llm_analysis"
    assert body["events"][0]["phase"] == "prepare_schema_snapshot"

    latest = client.get("/api/v1/admin/datasources/test-onboarding-db/onboarding/run")
    assert latest.status_code == 200, latest.text
    latest_body = latest.json()
    assert latest_body["id"] == body["id"]
    assert latest_body["status_message"] == "正在调用模型分析数据源。"


def test_run_onboarding_persists_profile_and_skill_packs(monkeypatch) -> None:
    async def _scenario() -> None:
        async with async_engine.begin() as conn:
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO datasources (id, display_name, dialect, connection_url, is_default)
                    VALUES (:id, :name, :dialect, :url, false)
                    """
                ),
                {
                    "id": "test-onboarding-db",
                    "name": "Sales Warehouse",
                    "dialect": "postgresql",
                    "url": "postgresql+psycopg://demo:secret@localhost:5432/sales",
                },
            )

        schema_payload, onboarding_profile = _sample_onboarding_inputs()
        monkeypatch.setattr(onboarding_agent, "introspect_schema_payload", lambda *_args: schema_payload)
        monkeypatch.setattr(
            onboarding_agent,
            "build_onboarding_profile_payload",
            lambda *_args: onboarding_profile,
        )

        async def _fake_llm_analysis(*_args, **_kwargs):
            return onboarding_agent.OnboardingAnalysisOutput(
                datasource_summary="Sales warehouse centers on orders and customers.",
                business_overview="The datasource tracks commercial transactions and customer context.",
                candidate_skill_packs=[
                    onboarding_agent.SkillPackDraft(
                        name="Order Performance",
                        slug="order-performance",
                        summary="Analyze order throughput, customer mix, and sales movement.",
                        business_overview="Focuses on orders joined with customer segmentation.",
                        schema_notes="Primary tables: orders, customers.",
                        keywords=["orders", "customers", "sales"],
                        table_focus=["orders", "customers"],
                        example_questions=["How many orders were created this week?"],
                        seed_documents=[
                            onboarding_agent.SkillDocumentDraft(
                                title="Order model notes",
                                content="orders joins customers on customer_id for segmentation analysis.",
                            )
                        ],
                        open_questions=[
                            onboarding_agent.OnboardingQuestion(
                                question="Does order status live in another table?",
                                reason="The sample profile did not expose status fields.",
                                priority=2,
                            )
                        ],
                        confidence=0.81,
                    )
                ],
                unresolved_questions=[
                    onboarding_agent.OnboardingQuestion(
                        question="Which revenue field is authoritative for sales reporting?",
                        reason="No monetary column was present in the sampled profile.",
                        priority=1,
                    )
                ],
                profile_highlights={"mode": "llm"},
            )

        monkeypatch.setattr(onboarding_agent, "llm_onboarding_analysis", _fake_llm_analysis)

        async with AsyncSessionLocal() as session:
            result = await onboarding_agent.run_onboarding_for_datasource(
                session,
                "test-onboarding-db",
                get_settings(),
            )

            assert result.datasource_id == "test-onboarding-db"
            assert result.analysis_status == "ready"
            assert result.summary == "Sales warehouse centers on orders and customers."

            profile = await session.get(DatasourceProfile, "test-onboarding-db")
            assert profile is not None
            assert profile.analysis_status == "ready"
            assert profile.profile_json["analysis"]["datasource_summary"] == (
                "Sales warehouse centers on orders and customers."
            )

            pack_rows = await session.execute(
                sa.select(SkillPack).where(SkillPack.datasource_id == "test-onboarding-db")
            )
            packs = list(pack_rows.scalars().all())
            assert len(packs) == 1
            assert packs[0].name == "Order Performance"

    anyio.run(_scenario)


def test_admin_analysis_workspace_returns_run_scoped_preview(client) -> None:
    async def _scenario() -> None:
        async with async_engine.begin() as conn:
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO datasources (id, display_name, dialect, connection_url, is_default)
                    VALUES (:id, :name, :dialect, :url, false)
                    """
                ),
                {
                    "id": "test-workspace-db",
                    "name": "Workspace DB",
                    "dialect": "postgresql",
                    "url": "postgresql+psycopg://demo:secret@localhost:5432/workspace",
                },
            )
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO datasource_profiles (datasource_id, summary, analysis_status, profile_json)
                    VALUES (:id, :summary, :status, CAST(:payload AS jsonb))
                    """
                ),
                {
                    "id": "test-workspace-db",
                    "summary": "workspace summary",
                    "status": "ready",
                    "payload": "{}",
                },
            )
            await conn.execute(
                sa.text(
                    """
                    INSERT INTO onboarding_runs (id, datasource_id, status, phase, status_message, result_payload, started_at)
                    VALUES (:id, :datasource_id, :status, :phase, :message, CAST(:payload AS jsonb), now())
                    """
                ),
                {
                    "id": "run-1",
                    "datasource_id": "test-workspace-db",
                    "status": "completed",
                    "phase": "complete",
                    "message": "技能包生成完成。",
                    "payload": """
                    {
                      "skill_pack_count": 1,
                      "domain_count": 1,
                      "preview_items": [
                        {
                          "name": "Retail Orders",
                          "domain_label": "Retail Orders",
                          "summary": "订单与退款分析",
                          "confidence": 0.82,
                          "status": "ready"
                        }
                      ],
                      "conversation": [
                        {
                          "role": "assistant",
                          "content": "请确认一个关键口径。",
                          "timestamp": "2026-04-11T07:20:00+00:00",
                          "question": {
                            "prompt": "零售订单是否包含退款单？",
                            "reason": "这会影响领域拆分",
                            "input_kind": "single_select",
                            "options": ["包含", "不包含"]
                          }
                        }
                      ]
                    }
                    """,
                },
            )

    anyio.run(_scenario)

    response = client.get("/api/v1/admin/datasources/test-workspace-db/analysis-workspace")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["selected_run_id"] == "run-1"
    assert body["result_preview"]["skill_pack_count"] == 1
    assert body["result_preview"]["preview_items"][0]["name"] == "Retail Orders"
    assert body["clarification"]["prompt"] == "零售订单是否包含退款单？"
