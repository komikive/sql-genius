"""Retrieval prefetch policy for the autonomous agent."""

from app.services.autonomous_agent import _should_prefetch_retrieval


def test_should_prefetch_retrieval_for_analytical_questions() -> None:
    assert _should_prefetch_retrieval("统计各门店近30天销售额排名") is True
    assert _should_prefetch_retrieval("How many claims were denied last month?") is True


def test_should_not_prefetch_retrieval_for_small_talk() -> None:
    assert _should_prefetch_retrieval("你好") is False
    assert _should_prefetch_retrieval("谢谢") is False
    assert _should_prefetch_retrieval("") is False
