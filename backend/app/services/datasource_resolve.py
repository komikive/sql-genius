"""Shared datasource resolution helpers for execution and admin flows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.db_url import normalize_database_driver_url
from app.db.models.datasource import Datasource

SUPPORTED_DIALECTS = {"mysql", "postgresql"}


@dataclass(slots=True)
class ResolvedDatasource:
    id: str
    label: str
    dialect: str | None
    connection_url: str
    is_default: bool
    source: str
    masked_url: str
    last_introspected_at: datetime | None = None


def infer_dialect(url: str | None) -> str | None:
    if not isinstance(url, str):
        return None
    if url.startswith("postgresql"):
        return "postgresql"
    if url.startswith("mysql") or "pymysql" in url:
        return "mysql"
    return None


def normalize_dialect(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_DIALECTS:
        raise HTTPException(status_code=400, detail="unsupported_dialect")
    return normalized


def mask_connection_url(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "***"


def load_env_datasources(datasources_json: str | None) -> list[ResolvedDatasource]:
    if not datasources_json or not datasources_json.strip():
        return []
    try:
        data = json.loads(datasources_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="datasources_invalid_json") from exc
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="datasources_not_configured")

    items: list[ResolvedDatasource] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        datasource_id = item.get("id")
        url = item.get("url")
        if not isinstance(datasource_id, str) or not datasource_id.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        label = item.get("name") or item.get("label") or datasource_id
        if not isinstance(label, str) or not label.strip():
            label = datasource_id
        normalized_url = normalize_database_driver_url(url)
        items.append(
            ResolvedDatasource(
                id=datasource_id.strip(),
                label=label.strip(),
                dialect=infer_dialect(normalized_url),
                connection_url=normalized_url,
                is_default=bool(item.get("default")) or index == 0,
                source="env",
                masked_url=mask_connection_url(normalized_url),
            )
        )
    return items


def normalize_connection_url(url: str) -> str:
    """Normalize datasource URLs to the installed sync drivers used by runtime tools."""
    return normalize_database_driver_url(url)


async def list_db_datasources(session: AsyncSession) -> list[Datasource]:
    try:
        result = await session.execute(
            select(Datasource)
            .options(selectinload(Datasource.schema_snapshot))
            .order_by(Datasource.display_name.asc(), Datasource.id.asc())
        )
    except SQLAlchemyError:
        return []
    return list(result.scalars().unique())


async def list_resolved_datasources(
    session: AsyncSession,
    settings: Settings,
) -> list[ResolvedDatasource]:
    env_items = {item.id: item for item in load_env_datasources(settings.sql_agent_datasources_json)}
    merged: dict[str, ResolvedDatasource] = dict(env_items)

    for row in await list_db_datasources(session):
        merged[row.id] = ResolvedDatasource(
            id=row.id,
            label=row.display_name,
            dialect=row.dialect,
            connection_url=normalize_connection_url(row.connection_url),
            is_default=row.is_default,
            source="db",
            masked_url=mask_connection_url(normalize_connection_url(row.connection_url)),
            last_introspected_at=(
                row.schema_snapshot.captured_at if row.schema_snapshot is not None else None
            ),
        )

    items = list(merged.values())
    if not any(item.is_default for item in items) and items:
        items[0].is_default = True
    return sorted(
        items,
        key=lambda item: (not item.is_default, item.label.lower(), item.id.lower()),
    )


async def resolve_datasource_url(
    session: AsyncSession,
    settings: Settings,
    datasource_id: str,
) -> str:
    try:
        row = await session.get(Datasource, datasource_id)
    except SQLAlchemyError:
        row = None
    if row is not None:
        return normalize_connection_url(row.connection_url)

    for item in load_env_datasources(settings.sql_agent_datasources_json):
        if item.id == datasource_id:
            return item.connection_url

    raise HTTPException(status_code=404, detail="datasource_not_found")


async def set_default_datasource(
    session: AsyncSession,
    datasource_id: str,
) -> None:
    await session.execute(
        update(Datasource)
        .where(Datasource.id != datasource_id, Datasource.is_default.is_(True))
        .values(is_default=False)
    )
