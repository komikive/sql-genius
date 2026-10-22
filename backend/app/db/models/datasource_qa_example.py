"""Datasource-scoped QA examples used for semantic retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.rag.constants import DEFAULT_EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource
    from app.db.models.skill_pack import SkillPack


class DatasourceQaExample(Base):
    """One retrievable QA example anchored to a datasource, optionally sourced from a skill pack."""

    __tablename__ = "datasource_qa_examples"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    datasource_id: Mapped[str] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_packs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scenario_tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="skill-pack")
    source_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    question_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIMENSION),
        nullable=True,
    )
    embedding_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_updated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    datasource: Mapped[Datasource] = relationship(back_populates="qa_examples")
    skill_pack: Mapped[SkillPack | None] = relationship(back_populates="qa_examples")
