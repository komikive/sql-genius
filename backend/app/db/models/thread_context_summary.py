"""Rolling thread summary used to compress long datasource-specific conversations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource


class ThreadContextSummary(Base):
    """Structured rolling summary for one thread and one datasource."""

    __tablename__ = "thread_context_summaries"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    datasource_id: Mapped[str] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rolling_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_status: Mapped[str] = mapped_column(String(32), nullable=False, default="fresh", index=True)
    summary_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summarized_turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compression_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_assistant_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_compacted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    datasource: Mapped[Datasource] = relationship(back_populates="thread_summaries")
