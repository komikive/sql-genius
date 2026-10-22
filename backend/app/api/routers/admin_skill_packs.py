"""Admin APIs for datasource-centered skill packs and canonical documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.db.models.skill_document import SkillDocument
from app.db.models.skill_pack import SkillPack

router = APIRouter()


class AdminSkillPackSummary(BaseModel):
    id: str
    datasource_id: str | None = None
    name: str
    slug: str
    status: str
    origin: str
    activation_mode: str
    confidence: float
    summary: str
    keywords: list[str]
    table_focus: list[str]
    created_at: datetime
    updated_at: datetime


class AdminSkillPackDetail(AdminSkillPackSummary):
    business_overview: str | None = None
    schema_notes: str | None = None
    metrics: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    business_rules: list[dict[str, Any]]
    pack_metadata: dict[str, Any] | None = None


class AdminSkillPackListResponse(BaseModel):
    items: list[AdminSkillPackSummary]


class AdminSkillPackUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    business_overview: str | None = None
    schema_notes: str | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)
    activation_mode: str | None = Field(default=None, min_length=1, max_length=32)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    keywords: list[str] | None = None
    table_focus: list[str] | None = None
    business_rules: list[dict[str, Any]] | None = None


class AdminSkillDocumentSummary(BaseModel):
    id: int
    skill_pack_id: str
    document_type: str
    title: str
    content: str
    source: str | None = None
    weight: float
    document_metadata: dict[str, Any] | None = None
    embedding_status: str
    embedding_error: str | None = None
    embedding_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdminSkillDocumentListResponse(BaseModel):
    items: list[AdminSkillDocumentSummary]


class AdminSkillDocumentCreateRequest(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source: str | None = Field(default=None, max_length=255)
    weight: float = Field(default=1.0, ge=0.1, le=3.0)
    document_metadata: dict[str, Any] | None = None


class AdminSkillDocumentUpdateRequest(BaseModel):
    document_type: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, max_length=255)
    weight: float | None = Field(default=None, ge=0.1, le=3.0)
    document_metadata: dict[str, Any] | None = None


def _to_skill_pack_summary(pack: SkillPack) -> AdminSkillPackSummary:
    return AdminSkillPackSummary(
        id=pack.id,
        datasource_id=pack.datasource_id,
        name=pack.name,
        slug=pack.slug,
        status=pack.status,
        origin=pack.origin,
        activation_mode=pack.activation_mode,
        confidence=float(pack.confidence),
        summary=pack.summary,
        keywords=pack.keywords or [],
        table_focus=pack.table_focus or [],
        created_at=pack.created_at,
        updated_at=pack.updated_at,
    )


def _to_skill_pack_detail(pack: SkillPack) -> AdminSkillPackDetail:
    return AdminSkillPackDetail(
        **_to_skill_pack_summary(pack).model_dump(),
        business_overview=pack.business_overview,
        schema_notes=pack.schema_notes,
        metrics=pack.metrics or [],
        entities=pack.entities or [],
        business_rules=pack.business_rules or [],
        pack_metadata=pack.pack_metadata,
    )


def _to_skill_document_summary(document: SkillDocument) -> AdminSkillDocumentSummary:
    return AdminSkillDocumentSummary(
        id=int(document.id),
        skill_pack_id=document.skill_pack_id,
        document_type=document.document_type,
        title=document.title,
        content=document.content,
        source=document.source,
        weight=float(document.weight),
        document_metadata=document.document_metadata,
        embedding_status=document.embedding_status,
        embedding_error=document.embedding_error,
        embedding_updated_at=document.embedding_updated_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("/admin/skill-packs", response_model=AdminSkillPackListResponse)
async def list_admin_skill_packs(
    datasource_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> AdminSkillPackListResponse:
    stmt = select(SkillPack).order_by(
        SkillPack.confidence.desc(),
        SkillPack.name.asc(),
        SkillPack.id.asc(),
    )
    if datasource_id:
        stmt = stmt.where(SkillPack.datasource_id == datasource_id)
    rows = await session.execute(stmt)
    return AdminSkillPackListResponse(
        items=[_to_skill_pack_summary(pack) for pack in rows.scalars().all()]
    )


@router.get("/admin/skill-packs/{skill_pack_id}", response_model=AdminSkillPackDetail)
async def get_admin_skill_pack(
    skill_pack_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminSkillPackDetail:
    pack = await session.get(SkillPack, skill_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="skill_pack_not_found")
    return _to_skill_pack_detail(pack)


@router.patch("/admin/skill-packs/{skill_pack_id}", response_model=AdminSkillPackDetail)
async def update_admin_skill_pack(
    skill_pack_id: str,
    body: AdminSkillPackUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminSkillPackDetail:
    pack = await session.get(SkillPack, skill_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="skill_pack_not_found")
    if body.name is not None:
        pack.name = body.name.strip()
    if body.summary is not None:
        pack.summary = body.summary.strip()
    if body.business_overview is not None:
        pack.business_overview = body.business_overview.strip() or None
    if body.schema_notes is not None:
        pack.schema_notes = body.schema_notes.strip() or None
    if body.status is not None:
        pack.status = body.status.strip()
    if body.activation_mode is not None:
        pack.activation_mode = body.activation_mode.strip()
    if body.confidence is not None:
        pack.confidence = float(body.confidence)
    if body.keywords is not None:
        pack.keywords = [item.strip() for item in body.keywords if item.strip()]
    if body.table_focus is not None:
        pack.table_focus = [item.strip() for item in body.table_focus if item.strip()]
    if body.business_rules is not None:
        pack.business_rules = body.business_rules
    await session.commit()
    await session.refresh(pack)
    return _to_skill_pack_detail(pack)


@router.delete("/admin/skill-packs/{skill_pack_id}", status_code=204)
async def delete_admin_skill_pack(
    skill_pack_id: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    pack = await session.get(SkillPack, skill_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="skill_pack_not_found")

    await session.execute(
        delete(SkillDocument).where(SkillDocument.skill_pack_id == skill_pack_id)
    )
    await session.delete(pack)
    await session.commit()


@router.get(
    "/admin/skill-packs/{skill_pack_id}/documents",
    response_model=AdminSkillDocumentListResponse,
)
async def list_admin_skill_documents(
    skill_pack_id: str,
    session: AsyncSession = Depends(get_db),
) -> AdminSkillDocumentListResponse:
    pack = await session.get(SkillPack, skill_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="skill_pack_not_found")
    rows = await session.execute(
        select(SkillDocument)
        .where(SkillDocument.skill_pack_id == skill_pack_id)
        .order_by(SkillDocument.weight.desc(), SkillDocument.id.asc())
    )
    return AdminSkillDocumentListResponse(
        items=[_to_skill_document_summary(row) for row in rows.scalars().all()]
    )


@router.post(
    "/admin/skill-packs/{skill_pack_id}/documents",
    response_model=AdminSkillDocumentSummary,
    status_code=201,
)
async def create_admin_skill_document(
    skill_pack_id: str,
    body: AdminSkillDocumentCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminSkillDocumentSummary:
    pack = await session.get(SkillPack, skill_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="skill_pack_not_found")
    row = SkillDocument(
        skill_pack_id=skill_pack_id,
        document_type=body.document_type.strip(),
        title=body.title.strip(),
        content=body.content.strip(),
        source=(body.source or "").strip() or "admin-skill-studio",
        weight=float(body.weight),
        document_metadata=body.document_metadata,
        embedding=None,
        embedding_status="pending",
        embedding_error=None,
        embedding_updated_at=None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_skill_document_summary(row)


@router.patch(
    "/admin/skill-documents/{document_id}",
    response_model=AdminSkillDocumentSummary,
)
async def update_admin_skill_document(
    document_id: int,
    body: AdminSkillDocumentUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminSkillDocumentSummary:
    row = await session.get(SkillDocument, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="skill_document_not_found")
    if body.document_type is not None:
        row.document_type = body.document_type.strip()
    if body.title is not None:
        row.title = body.title.strip()
    if body.content is not None:
        row.content = body.content.strip()
        row.embedding = None
        row.embedding_status = "pending"
        row.embedding_error = None
        row.embedding_updated_at = None
    if body.source is not None:
        row.source = body.source.strip() or None
    if body.weight is not None:
        row.weight = float(body.weight)
    if body.document_metadata is not None:
        row.document_metadata = body.document_metadata
    await session.commit()
    await session.refresh(row)
    return _to_skill_document_summary(row)


@router.delete("/admin/skill-documents/{document_id}", status_code=204)
async def delete_admin_skill_document(
    document_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    row = await session.get(SkillDocument, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="skill_document_not_found")
    await session.delete(row)
    await session.commit()


