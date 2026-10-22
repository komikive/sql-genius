"""Datasource records managed from the admin surface (Phase 6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.datasource_memory_document import DatasourceMemoryDocument
    from app.db.models.datasource_profile import DatasourceProfile
    from app.db.models.datasource_qa_example import DatasourceQaExample
    from app.db.models.datasource_schema_snapshot import DatasourceSchemaSnapshot
    from app.db.models.skill_pack import SkillPack
    from app.db.models.thread_context_summary import ThreadContextSummary
    from app.db.models.thread_conversation_turn import ThreadConversationTurn


class Datasource(Base):
    """Persisted datasource definition used by admin and execution flows."""

    __tablename__ = "datasources"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dialect: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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

    schema_snapshot: Mapped[DatasourceSchemaSnapshot | None] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
        uselist=False,
    )
    profile: Mapped[DatasourceProfile | None] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
        uselist=False,
    )
    skill_packs: Mapped[list[SkillPack]] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
    )
    memory_document: Mapped[DatasourceMemoryDocument | None] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
        uselist=False,
    )
    qa_examples: Mapped[list[DatasourceQaExample]] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
    )
    thread_summaries: Mapped[list[ThreadContextSummary]] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
    )
    conversation_turns: Mapped[list[ThreadConversationTurn]] = relationship(
        back_populates="datasource",
        cascade="all, delete-orphan",
    )
