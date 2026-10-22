"""Canonical markdown memory document for one datasource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource


class DatasourceMemoryDocument(Base):
    """Single long-lived memory document maintained autonomously by the agent."""

    __tablename__ = "datasource_memory_documents"

    datasource_id: Mapped[str] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="主记忆文档")
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_outline: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    document_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
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

    datasource: Mapped[Datasource] = relationship(back_populates="memory_document")
