"""Admin datasource CRUD, connection testing, and schema introspection."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.db.models.datasource import Datasource
from app.db.models.datasource_memory_document import DatasourceMemoryDocument
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
from app.db.models.onboarding_run import OnboardingRun
from app.db.models.skill_pack import SkillPack
from app.db.models.thread_context_summary import ThreadContextSummary
from app.services.datasource_introspection import (
    introspect_schema_payload as _introspect_schema_payload,
)
from app.services.datasource_introspection import run_connection_probe as _run_connection_probe
from app.services.onboarding_chat import onboarding_chat_stream
from app.services.onboarding_runs import (
    get_active_onboarding_run,
    get_latest_onboarding_run,
    start_onboarding_run,
)
from app.services.datasource_resolve import (
    mask_connection_url,
    normalize_dialect,
    normalize_connection_url,
    resolve_datasource_url,
    set_default_datasource,
)

router = APIRouter()

class AdminDatasourceSummary(BaseModel):
    id: str
    display_name: str
    dialect: Literal["mysql", "postgresql"]
    is_default: bool
    connection_url_masked: str
    last_introspected_at: datetime | None = None


class AdminDatasourceDetail(AdminDatasourceSummary):
    has_connection_url: bool
    schema_available: bool


class AdminDatasourceListResponse(BaseModel):
    items: list[AdminDatasourceSummary]


class AdminDatasourceCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    dialect: Literal["mysql", "postgresql"]
    connection_url: str = Field(..., min_length=1)
    is_default: bool = False


class AdminDatasourceUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    dialect: Literal["mysql", "postgresql"] | None = None
    connection_url: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None


class AdminDatasourceTestRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1)
    connection_url: str | None = Field(default=None, min_length=1)
    dialect: Literal["mysql", "postgresql"] | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "AdminDatasourceTestRequest":
        if self.id:
            return self
        if self.connection_url and self.dialect:
            return self
        raise ValueError("provide id or connection_url+dialect")


class AdminDatasourceTestResponse(BaseModel):
    ok: bool
    message: str


class AdminDatasourceIntrospectResponse(BaseModel):
    ok: bool
    message: str
    captured_at: datetime
    table_count: int
    column_count: int
    truncated: bool


class AdminSkillPackSummary(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    confidence: float
    origin: str
    summary: str


class AdminDatasourceProfileResponse(BaseModel):
    datasource_id: str
    analysis_status: str
    summary: str
    analysis_error: str | None = None
    last_analyzed_at: datetime | None = None
    profile_json: dict[str, Any] | None = None
    active_memory_count: int = 0
    thread_summary_count: int = 0
    draft_skill_count: int = 0
    skill_packs: list[AdminSkillPackSummary] = Field(default_factory=list)


class AdminOnboardingRunEvent(BaseModel):
    timestamp: str
    phase: str
    message: str
    level: str = "info"
    payload: dict[str, Any] | None = None


class AdminOnboardingRunResponse(BaseModel):
    id: str
    datasource_id: str
    status: str
    phase: str
    status_message: str
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    events: list[AdminOnboardingRunEvent] = Field(default_factory=list)
    result_payload: dict[str, Any] | None = None


class AdminOnboardingRunListResponse(BaseModel):
    items: list[AdminOnboardingRunResponse]


class AdminOnboardingContextQuestion(BaseModel):
    question: str
    answer: str = ""


class AdminOnboardingContextUpdateRequest(BaseModel):
    notes: str = ""
    questions: list[AdminOnboardingContextQuestion] = Field(default_factory=list)


class AdminOnboardingContextResponse(BaseModel):
    datasource_id: str
    notes: str = ""
    questions: list[AdminOnboardingContextQuestion] = Field(default_factory=list)
    conversation: list[dict[str, Any]] = Field(default_factory=list)


class AdminOnboardingChatStreamRequest(BaseModel):
    message: str | None = None
    run_id: str | None = None


class AdminAnalysisWorkspaceHistoryItem(BaseModel):
    run_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    phase: str
    headline: str
    clarification_pending: bool = False
    preview_available: bool = False


class AdminAnalysisWorkspaceClarification(BaseModel):
    prompt: str
    reason: str = ""
    input_kind: str = "text"
    options: list[str] = Field(default_factory=list)


class AdminAnalysisWorkspaceResponse(BaseModel):
    datasource: AdminDatasourceDetail
    active_run: AdminOnboardingRunResponse | None = None
    status: str
    timeline_items: list[AdminOnboardingRunEvent] = Field(default_factory=list)
    clarification: AdminAnalysisWorkspaceClarification | None = None
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    result_preview: dict[str, Any] | None = None
    history: list[AdminAnalysisWorkspaceHistoryItem] = Field(default_factory=list)
    debug_available: bool = False
    selected_run_id: str | None = None


def _to_summary(row: Datasource) -> AdminDatasourceSummary:
    snapshot = row.schema_snapshot
    return AdminDatasourceSummary(
        id=row.id,
        display_name=row.display_name,
        dialect=normalize_dialect(row.dialect),
        is_default=bool(row.is_default),
        connection_url_masked=mask_connection_url(row.connection_url),
        last_introspected_at=(
            snapshot.captured_at if snapshot is not None else None
        ),
    )


def _to_detail(row: Datasource) -> AdminDatasourceDetail:
    summary = _to_summary(row)
    return AdminDatasourceDetail(
        **summary.model_dump(),
        has_connection_url=bool(row.connection_url),
        schema_available=row.schema_snapshot is not None,
    )


def _build_profile_response(
    datasource_id: str,
    profile: DatasourceProfile | None,
    skill_packs: list[SkillPack],
    *,
    active_memory_count: int = 0,
    thread_summary_count: int = 0,
    draft_skill_count: int = 0,
) -> AdminDatasourceProfileResponse:
    return AdminDatasourceProfileResponse(
        datasource_id=datasource_id,
        analysis_status=profile.analysis_status if profile is not None else "pending",
        summary=profile.summary if profile is not None else "",
        analysis_error=profile.analysis_error if profile is not None else None,
        last_analyzed_at=profile.last_analyzed_at if profile is not None else None,
        profile_json=profile.profile_json if profile is not None else None,
        active_memory_count=active_memory_count,
        thread_summary_count=thread_summary_count,
        draft_skill_count=draft_skill_count,
        skill_packs=[
            AdminSkillPackSummary(
                id=row.id,
                name=row.name,
                slug=row.slug,
                status=row.status,
                confidence=float(row.confidence),
                origin=row.origin,
                summary=row.summary,
            )
            for row in skill_packs
        ],
    )


def _build_onboarding_run_response(run: OnboardingRun) -> AdminOnboardingRunResponse:
    raw_events = run.events if isinstance(run.events, list) else []
    events = [
        AdminOnboardingRunEvent(
            timestamp=str(item.get("timestamp") or ""),
            phase=str(item.get("phase") or run.phase),
            message=str(item.get("message") or ""),
            level=str(item.get("level") or "info"),
            payload=item.get("payload") if isinstance(item.get("payload"), dict) else None,
        )
        for item in raw_events
        if isinstance(item, dict)
    ]
    return AdminOnboardingRunResponse(
        id=run.id,
        datasource_id=run.datasource_id,
        status=run.status,
        phase=run.phase,
        status_message=run.status_message,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        events=events,
        result_payload=run.result_payload if isinstance(run.result_payload, dict) else None,
    )


def _build_onboarding_context_response(
    datasource_id: str,
    payload: dict[str, Any] | None,
) -> AdminOnboardingContextResponse:
    raw = payload if isinstance(payload, dict) else {}
    raw_questions = raw.get("questions") if isinstance(raw.get("questions"), list) else []
    questions = [
        AdminOnboardingContextQuestion(
            question=str(item.get("question") or ""),
            answer=str(item.get("answer") or ""),
        )
        for item in raw_questions
        if isinstance(item, dict) and str(item.get("question") or "").strip()
    ]
    return AdminOnboardingContextResponse(
        datasource_id=datasource_id,
        notes=str(raw.get("notes") or ""),
        questions=questions,
        conversation=[
            item
            for item in (raw.get("conversation") or [])
            if isinstance(item, dict)
        ][:24],
    )


def _extract_workspace_clarification(
    context_payload: dict[str, Any] | None,
) -> AdminAnalysisWorkspaceClarification | None:
    if not isinstance(context_payload, dict):
        return None
    raw_conversation = context_payload.get("conversation")
    if not isinstance(raw_conversation, list):
        return None
    latest = raw_conversation[-1] if raw_conversation else None
    if not isinstance(latest, dict) or latest.get("role") != "assistant":
        return None
    raw_question = latest.get("question")
    if not isinstance(raw_question, dict):
        return None
    prompt = str(raw_question.get("prompt") or "").strip()
    if not prompt:
        return None
    return AdminAnalysisWorkspaceClarification(
        prompt=prompt,
        reason=str(raw_question.get("reason") or ""),
        input_kind=str(raw_question.get("input_kind") or "text"),
        options=[
            str(value)
            for value in (raw_question.get("options") or [])
            if isinstance(value, str)
        ],
    )


def _build_workspace_history_item(
    run: OnboardingRun,
    *,
    clarification_pending: bool,
) -> AdminAnalysisWorkspaceHistoryItem:
    result_payload = run.result_payload if isinstance(run.result_payload, dict) else {}
    preview_items = result_payload.get("preview_items")
    preview_available = isinstance(preview_items, list) and len(preview_items) > 0
    return AdminAnalysisWorkspaceHistoryItem(
        run_id=run.id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        phase=run.phase,
        headline=run.status_message,
        clarification_pending=clarification_pending,
        preview_available=preview_available,
    )


async def _load_profile_counters(
    session: AsyncSession,
    datasource_id: str,
) -> dict[str, int]:
    memory_count = await session.scalar(
        select(func.count())
        .select_from(DatasourceMemoryDocument)
        .where(DatasourceMemoryDocument.datasource_id == datasource_id)
    )
    summary_count = await session.scalar(
        select(func.count())
        .select_from(ThreadContextSummary)
        .where(ThreadContextSummary.datasource_id == datasource_id)
    )
    draft_skill_count = await session.scalar(
        select(func.count())
        .select_from(SkillPack)
        .where(SkillPack.datasource_id == datasource_id)
        .where(SkillPack.origin == "runtime-learning")
        .where(SkillPack.status == "draft")
    )
    return {
        "active_memory_count": int(memory_count or 0),
        "thread_summary_count": int(summary_count or 0),
        "draft_skill_count": int(draft_skill_count or 0),
    }


@router.get("/admin/datasources", response_model=AdminDatasourceListResponse)
async def list_admin_datasources(
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceListResponse:
    rows = await session.execute(
        text(
            """
            SELECT
              d.id,
              d.display_name,
              d.dialect,
              d.connection_url,
              d.is_default,
              s.captured_at
            FROM datasources d
            LEFT JOIN datasource_schema_snapshots s ON s.datasource_id = d.id
            ORDER BY d.is_default DESC, d.display_name ASC, d.id ASC
            """
        )
    )
    items = [
        AdminDatasourceSummary(
            id=row.id,
            display_name=row.display_name,
            dialect=normalize_dialect(row.dialect),
            is_default=bool(row.is_default),
            connection_url_masked=mask_connection_url(row.connection_url),
            last_introspected_at=row.captured_at,
        )
        for row in rows
    ]
    return AdminDatasourceListResponse(items=items)


@router.get("/admin/onboarding-runs", response_model=AdminOnboardingRunListResponse)
async def list_admin_onboarding_runs(
    datasource_id: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
) -> AdminOnboardingRunListResponse:
    stmt = select(OnboardingRun).order_by(OnboardingRun.created_at.desc(), OnboardingRun.id.desc())
    if datasource_id:
        stmt = stmt.where(OnboardingRun.datasource_id == datasource_id)
    stmt = stmt.limit(min(max(limit, 1), 100))
    result = await session.execute(stmt)
    return AdminOnboardingRunListResponse(
        items=[_build_onboarding_run_response(row) for row in result.scalars().all()]
    )


@router.get("/admin/onboarding-runs/{run_id}", response_model=AdminOnboardingRunResponse)
async def get_admin_onboarding_run(
    run_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminOnboardingRunResponse:
    run = await session.get(OnboardingRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="onboarding_run_not_found")
    return _build_onboarding_run_response(run)


@router.get(
    "/admin/datasources/{datasource_id}/analysis-workspace",
    response_model=AdminAnalysisWorkspaceResponse,
)
async def get_admin_datasource_analysis_workspace(
    datasource_id: str,
    run_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> AdminAnalysisWorkspaceResponse:
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")
    await session.refresh(datasource, attribute_names=["schema_snapshot"])

    profile = await session.get(DatasourceProfile, datasource_id)
    history_result = await session.execute(
        select(OnboardingRun)
        .where(OnboardingRun.datasource_id == datasource_id)
        .order_by(OnboardingRun.created_at.desc(), OnboardingRun.id.desc())
        .limit(30)
    )
    history_runs = list(history_result.scalars().all())
    active_run = await get_active_onboarding_run(session, datasource_id)

    selected_run: OnboardingRun | None = None
    if run_id:
        selected_run = next((item for item in history_runs if item.id == run_id), None)
    if selected_run is None:
        selected_run = active_run or (history_runs[0] if history_runs else None)

    timeline_items: list[AdminOnboardingRunEvent] = []
    result_preview: dict[str, Any] | None = None
    if selected_run is not None:
        selected_run_response = _build_onboarding_run_response(selected_run)
        timeline_items = selected_run_response.events
        result_preview = selected_run_response.result_payload
    else:
        selected_run_response = None

    selected_result_payload = selected_run.result_payload if selected_run and isinstance(selected_run.result_payload, dict) else {}
    context_payload = {"conversation": selected_result_payload.get("conversation") or []}
    clarification = _extract_workspace_clarification(context_payload)

    history = [
        _build_workspace_history_item(
            run,
            clarification_pending=run.status in {"waiting_for_clarification", "resuming"},
        )
        for run in history_runs
    ]

    status = "idle"
    if selected_run is not None:
        if clarification is not None and selected_run.status in {"running", "waiting_for_clarification", "resuming"}:
            status = "waiting_for_clarification"
        else:
            status = selected_run.status
    elif profile is not None and profile.analysis_status == "analysis_failed":
        status = "failed"

    return AdminAnalysisWorkspaceResponse(
        datasource=_to_detail(datasource),
        active_run=_build_onboarding_run_response(active_run) if active_run is not None else None,
        status=status,
        timeline_items=timeline_items,
        clarification=clarification,
        conversation=[
            item for item in (context_payload.get("conversation") or [])
            if isinstance(item, dict)
        ][:24],
        result_preview=result_preview,
        history=history,
        debug_available=bool(timeline_items),
        selected_run_id=selected_run.id if selected_run is not None else None,
    )


@router.get("/admin/datasources/{datasource_id}", response_model=AdminDatasourceDetail)
async def get_admin_datasource(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceDetail:
    row = await session.get(Datasource, datasource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")
    await session.refresh(row, attribute_names=["schema_snapshot"])
    return _to_detail(row)


@router.post("/admin/datasources", response_model=AdminDatasourceDetail, status_code=201)
async def create_admin_datasource(
    body: AdminDatasourceCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceDetail:
    if await session.get(Datasource, body.id.strip()) is not None:
        raise HTTPException(status_code=409, detail="datasource_already_exists")

    row = Datasource(
        id=body.id.strip(),
        display_name=body.display_name.strip(),
        dialect=normalize_dialect(body.dialect),
        connection_url=normalize_connection_url(body.connection_url),
        is_default=body.is_default,
    )
    session.add(row)
    await session.flush()
    if row.is_default:
        await set_default_datasource(session, row.id)
    await session.commit()
    await session.refresh(row, attribute_names=["schema_snapshot"])
    return _to_detail(row)


@router.patch("/admin/datasources/{datasource_id}", response_model=AdminDatasourceDetail)
async def update_admin_datasource(
    datasource_id: str,
    body: AdminDatasourceUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceDetail:
    row = await session.get(Datasource, datasource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")

    if body.display_name is not None:
        row.display_name = body.display_name.strip()
    if body.dialect is not None:
        row.dialect = normalize_dialect(body.dialect)
    if body.connection_url is not None:
        row.connection_url = normalize_connection_url(body.connection_url)
    if body.is_default is not None:
        row.is_default = body.is_default

    await session.flush()
    if row.is_default:
        await set_default_datasource(session, row.id)
    await session.commit()
    await session.refresh(row, attribute_names=["schema_snapshot"])
    return _to_detail(row)


@router.delete("/admin/datasources/{datasource_id}", status_code=204)
async def delete_admin_datasource(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    row = await session.get(Datasource, datasource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")
    await session.delete(row)
    await session.commit()


@router.post("/admin/datasources/test", response_model=AdminDatasourceTestResponse)
async def test_admin_datasource(
    body: AdminDatasourceTestRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceTestResponse:
    settings = get_settings()
    if body.id:
        connection_url = await resolve_datasource_url(session, settings, body.id.strip())
    else:
        connection_url = normalize_connection_url(body.connection_url)

    ok, message = await anyio.to_thread.run_sync(_run_connection_probe, connection_url)
    return AdminDatasourceTestResponse(ok=ok, message=message)


@router.post(
    "/admin/datasources/{datasource_id}/introspect",
    response_model=AdminDatasourceIntrospectResponse,
)
async def introspect_admin_datasource(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceIntrospectResponse:
    row = await session.get(Datasource, datasource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")

    payload = await anyio.to_thread.run_sync(
        _introspect_schema_payload,
        row.connection_url,
        normalize_dialect(row.dialect),
    )
    captured_at = datetime.now(timezone.utc)

    snapshot = await session.get(DatasourceSchemaSnapshot, row.id)
    if snapshot is None:
        snapshot = DatasourceSchemaSnapshot(
            datasource_id=row.id,
            payload=payload,
            captured_at=captured_at,
        )
        session.add(snapshot)
    else:
        snapshot.payload = payload
        snapshot.captured_at = captured_at

    await session.commit()
    return AdminDatasourceIntrospectResponse(
        ok=True,
        message="Schema snapshot captured",
        captured_at=captured_at,
        table_count=int(payload.get("table_count", 0)),
        column_count=int(payload.get("column_count", 0)),
        truncated=bool(payload.get("truncated", False)),
    )


@router.get("/admin/datasources/{datasource_id}/schema")
async def get_admin_datasource_schema(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    snapshot = await session.get(DatasourceSchemaSnapshot, datasource_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="datasource_schema_not_found")
    return snapshot.payload


@router.get(
    "/admin/datasources/{datasource_id}/profile",
    response_model=AdminDatasourceProfileResponse,
)
async def get_admin_datasource_profile(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminDatasourceProfileResponse:
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")

    profile = await session.get(DatasourceProfile, datasource_id)
    pack_rows = await session.execute(
        select(SkillPack)
        .where(SkillPack.datasource_id == datasource_id)
        .order_by(SkillPack.confidence.desc(), SkillPack.name.asc(), SkillPack.id.asc())
    )
    counters = await _load_profile_counters(session, datasource_id)
    return _build_profile_response(
        datasource_id,
        profile,
        list(pack_rows.scalars().all()),
        **counters,
    )


@router.get(
    "/admin/datasources/{datasource_id}/onboarding/context",
    response_model=AdminOnboardingContextResponse,
)
async def get_admin_datasource_onboarding_context(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminOnboardingContextResponse:
    profile = await session.get(DatasourceProfile, datasource_id)
    if profile is None:
        return AdminOnboardingContextResponse(datasource_id=datasource_id)
    raw = profile.profile_json.get("onboarding_context") if isinstance(profile.profile_json, dict) else None
    return _build_onboarding_context_response(datasource_id, raw if isinstance(raw, dict) else None)


@router.put(
    "/admin/datasources/{datasource_id}/onboarding/context",
    response_model=AdminOnboardingContextResponse,
)
async def update_admin_datasource_onboarding_context(
    datasource_id: str,
    body: AdminOnboardingContextUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminOnboardingContextResponse:
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise HTTPException(status_code=404, detail="datasource_not_found")

    profile = await session.get(DatasourceProfile, datasource_id)
    if profile is None:
        profile = DatasourceProfile(datasource_id=datasource_id)
        session.add(profile)

    payload = dict(profile.profile_json or {}) if isinstance(profile.profile_json, dict) else {}
    existing_context = payload.get("onboarding_context") if isinstance(payload.get("onboarding_context"), dict) else {}
    payload["onboarding_context"] = {
        "notes": body.notes.strip(),
        "questions": [
            {"question": item.question.strip(), "answer": item.answer.strip()}
            for item in body.questions
            if item.question.strip()
        ],
        "conversation": existing_context.get("conversation") if isinstance(existing_context.get("conversation"), list) else [],
    }
    profile.profile_json = payload
    await session.commit()
    return _build_onboarding_context_response(datasource_id, payload["onboarding_context"])


@router.post("/admin/datasources/{datasource_id}/onboarding/chat/stream")
async def stream_admin_datasource_onboarding_chat(
    datasource_id: str,
    body: AdminOnboardingChatStreamRequest,
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    async def _stream() -> AsyncIterator[bytes]:
        async for chunk in onboarding_chat_stream(
            session,
            datasource_id=datasource_id,
            user_message=body.message,
            run_id=body.run_id,
            settings=get_settings(),
        ):
            yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get(
    "/admin/datasources/{datasource_id}/onboarding/run",
    response_model=AdminOnboardingRunResponse,
)
async def get_admin_datasource_onboarding_run(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminOnboardingRunResponse:
    run = await get_latest_onboarding_run(session, datasource_id)
    if run is None:
        raise HTTPException(status_code=404, detail="datasource_onboarding_run_not_found")
    return _build_onboarding_run_response(run)


@router.post(
    "/admin/datasources/{datasource_id}/onboarding/run",
    response_model=AdminOnboardingRunResponse,
    status_code=202,
)
async def run_admin_datasource_onboarding(
    datasource_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminOnboardingRunResponse:
    try:
        run = await start_onboarding_run(session, datasource_id, get_settings())
    except ValueError as exc:
        if str(exc) == "datasource_not_found":
            raise HTTPException(status_code=404, detail="datasource_not_found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_onboarding_run_response(run)
