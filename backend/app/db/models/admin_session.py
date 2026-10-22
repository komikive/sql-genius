"""Lightweight chat-thread registry for admin browsing."""

from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminSession(Base):
    """Admin-visible session/thread summary independent of checkpoint internals."""

    __tablename__ = "admin_sessions"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_activity_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
