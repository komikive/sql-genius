"""Datasource-centered skill packs used by onboarding and runtime agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, JSON, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.rag.constants import DEFAULT_EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource
    from app.db.models.datasource_qa_example import DatasourceQaExample
    from app.db.models.skill_document import SkillDocument


class SkillPack(Base):
    """Structured, loadable business skill derived from one datasource."""

    __tablename__ = "skill_packs"
    __table_args__ = (
        UniqueConstraint("datasource_id", "slug", name="uq_skill_packs_datasource_slug"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    datasource_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="onboarding")
    activation_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    keywords: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    entities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    table_focus: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    business_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    example_sql_pairs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    example_questions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    pack_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    summary_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(DEFAULT_EMBEDDING_DIMENSION),
        nullable=True,
    )
    embedding_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_updated_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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

    datasource: Mapped[Datasource | None] = relationship(back_populates="skill_packs")
    documents: Mapped[list[SkillDocument]] = relationship(
        back_populates="skill_pack",
        cascade="all, delete-orphan",
    )
    qa_examples: Mapped[list[DatasourceQaExample]] = relationship(
        back_populates="skill_pack"
    )
