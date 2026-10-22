import pytest

from app.core.thread_guard import ThreadRunGuard


@pytest.mark.asyncio
async def test_thread_guard_allows_only_one_active_run_per_thread() -> None:
    guard = ThreadRunGuard()

    assert await guard.try_acquire("thread-1") is True
    assert await guard.try_acquire("thread-1") is False
    assert await guard.try_acquire("thread-2") is True

    await guard.release("thread-1")
    assert await guard.try_acquire("thread-1") is True
