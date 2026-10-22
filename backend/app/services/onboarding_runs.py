"""Background orchestration and persisted progress for datasource onboarding."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import AsyncSessionLocal
from app.db.models.datasource import Datasource
from app.db.models.datasource_profile import DatasourceProfile
from app.db.models.onboarding_run import OnboardingRun
from app.services.datasource_introspection import sanitize_error_message
from app.services.onboarding_agent import run_onboarding_for_datasource

ProgressReporter = Callable[[str, str, dict[str, Any] | None], Awaitable[None]]

ACTIVE_RUN_STATUSES = {"queued", "running", "waiting_for_clarification", "resuming"}
CHAT_RUN_STATUSES = ACTIVE_RUN_STATUSES | {"completed", "failed"}
MAX_EVENT_COUNT = 80


def _append_event(
    run: OnboardingRun,
    *,
    phase: str,
    message: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    events = list(run.events or [])
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "message": message,
        "level": level,
    }
    if payload:
        event["payload"] = payload
    events.append(event)
    run.events = events[-MAX_EVENT_COUNT:]


async def _record_run_progress(
    run_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    message: str | None = None,
    level: str = "info",
    payload: dict[str, Any] | None = None,
    error: str | None = None,
    result_patch: dict[str, Any] | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        run = await session.get(OnboardingRun, run_id)
        if run is None:
            return

        if status is not None:
            run.status = status
        if phase is not None:
            run.phase = phase
        if message is not None:
            run.status_message = message
            _append_event(run, phase=phase or run.phase, message=message, level=level, payload=payload)
        elif payload:
            _append_event(
                run,
                phase=phase or run.phase,
                message=run.status_message or (phase or run.phase),
                level=level,
                payload=payload,
            )
        if error is not None:
            run.error = error
        if result_patch:
            merged = dict(run.result_payload or {})
            merged.update(result_patch)
            run.result_payload = merged

        if run.status in {"completed", "failed", "cancelled"} and run.completed_at is None:
            run.completed_at = datetime.now(timezone.utc)
        await session.commit()


async def _run_onboarding_in_background(
    *,
    run_id: str,
    datasource_id: str,
    settings: Settings,
) -> None:
    await _record_run_progress(
        run_id,
        status="running",
        phase="prepare",
        message="后台分析任务已启动。",
    )

    async def progress(phase: str, message: str, payload: dict[str, Any] | None = None) -> None:
        await _record_run_progress(run_id, phase=phase, message=message, payload=payload)

    try:
        async with AsyncSessionLocal() as session:
            result = await run_onboarding_for_datasource(
                session,
                datasource_id,
                settings,
                progress_callback=progress,
            )
    except Exception as exc:
        await _record_run_progress(
            run_id,
            status="failed",
            phase="failed",
            message="后台分析失败。",
            level="error",
            error=sanitize_error_message(exc),
        )
        return

    await _record_run_progress(
        run_id,
        status="completed",
        phase="complete",
        message="技能包生成完成。",
        result_patch={
            "analysis_status": result.analysis_status,
            "summary": result.summary,
            "skill_pack_count": result.skill_pack_count,
            "unresolved_question_count": result.unresolved_question_count,
            "domain_count": result.domain_count,
            "preview_items": [item.model_dump() for item in result.preview_items],
        },
    )


async def get_latest_onboarding_run(
    session: AsyncSession,
    datasource_id: str,
) -> OnboardingRun | None:
    result = await session.execute(
        select(OnboardingRun)
        .where(OnboardingRun.datasource_id == datasource_id)
        .order_by(OnboardingRun.created_at.desc(), OnboardingRun.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_active_onboarding_run(
    session: AsyncSession,
    datasource_id: str,
) -> OnboardingRun | None:
    result = await session.execute(
        select(OnboardingRun)
        .where(OnboardingRun.datasource_id == datasource_id)
        .where(OnboardingRun.status.in_(ACTIVE_RUN_STATUSES))
        .order_by(OnboardingRun.created_at.desc(), OnboardingRun.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def start_onboarding_run(
    session: AsyncSession,
    datasource_id: str,
    settings: Settings,
) -> OnboardingRun:
    """创建后台 onboarding 任务：schema 采集 → LLM 技能包起草 → 写入 Skill Studio。

    同一数据源同时仅允许一个 active run；进度写入 onboarding_runs.events 供 Admin 时间线展示。
    """
    datasource = await session.get(Datasource, datasource_id)
    if datasource is None:
        raise ValueError("datasource_not_found")

    existing = await session.execute(
        select(OnboardingRun)
        .where(OnboardingRun.datasource_id == datasource_id)
        .where(OnboardingRun.status.in_(ACTIVE_RUN_STATUSES))
        .order_by(OnboardingRun.created_at.desc(), OnboardingRun.id.desc())
        .limit(1)
    )
    active_run = existing.scalars().first()
    if active_run is not None:
        return active_run

    profile = await session.get(DatasourceProfile, datasource_id)
    if profile is None:
        profile = DatasourceProfile(datasource_id=datasource_id)
        session.add(profile)
    profile.analysis_status = "running"
    profile.analysis_error = None

    run = OnboardingRun(
        datasource_id=datasource_id,
        status="queued",
        phase="queued",
        status_message="分析任务已进入队列。",
        started_at=datetime.now(timezone.utc),
        events=[],
        result_payload={"conversation": [], "preview_items": []},
    )
    _append_event(run, phase="queued", message="分析任务已创建，等待后台执行。")
    session.add(run)
    await session.commit()

    asyncio.get_running_loop().create_task(
        _run_onboarding_in_background(run_id=run.id, datasource_id=datasource_id, settings=settings)
    )
    return run
