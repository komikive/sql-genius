"""Skill-scoped documents used for retrieval and runtime grounding."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.rag.constants import DEFAULT_EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from app.db.models.skill_pack import SkillPack


class SkillDocument(Base):
    """One retrievable document or note attached to a skill pack."""

    __tablename__ = "skill_documents"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    skill_pack_id: Mapped[str] = mapped_column(
        ForeignKey("skill_packs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weight: Mapped[float] = mapped_column(nullable=False, default=1.0)
    document_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
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

    skill_pack: Mapped[SkillPack] = relationship(back_populates="documents")
