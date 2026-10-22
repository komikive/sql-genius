"""Persisted datasource profile produced by the onboarding agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, JSON, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource


class DatasourceProfile(Base):
    """One profile per datasource capturing analysis status and rich summary data."""

    __tablename__ = "datasource_profiles"

    datasource_id: Mapped[str] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    profile_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    analysis_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
    )
    analysis_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_analyzed_at: Mapped[object | None] = mapped_column(
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

    datasource: Mapped[Datasource] = relationship(back_populates="profile")
