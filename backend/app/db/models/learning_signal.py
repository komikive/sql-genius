"""Buffered learning signals for new-domain accumulation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.datasource import Datasource


class LearningSignal(Base):
    """A buffered pattern that may indicate a new business domain worth a skill pack."""

    __tablename__ = "learning_signals"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    datasource_id: Mapped[str] = mapped_column(
        ForeignKey("datasources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pattern_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    datasource: Mapped[Datasource] = relationship()
