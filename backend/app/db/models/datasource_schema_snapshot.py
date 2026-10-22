"""Persisted datasource schema snapshot for admin visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource


class DatasourceSchemaSnapshot(Base):
    """Latest captured schema payload for a datasource."""

    __tablename__ = "datasource_schema_snapshots"

    datasource_id: Mapped[str] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    captured_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    datasource: Mapped[Datasource] = relationship(back_populates="schema_snapshot")
