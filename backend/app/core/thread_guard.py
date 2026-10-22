"""Single-flight guard for concurrent runs on one LangGraph thread."""

from __future__ import annotations

import asyncio


class ThreadRunGuard:
    def __init__(self) -> None:
        self._active: set[str] = set()
        self._lock = asyncio.Lock()

    async def try_acquire(self, thread_id: str) -> bool:
        async with self._lock:
            if thread_id in self._active:
                return False
            self._active.add(thread_id)
            return True

    async def release(self, thread_id: str) -> None:
        async with self._lock:
            self._active.discard(thread_id)
