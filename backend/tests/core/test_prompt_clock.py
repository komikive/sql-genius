from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.prompt_clock import (
    build_prompt_clock_context,
    format_prompt_clock,
    resolve_prompt_timezone,
)


def test_format_prompt_clock_fixed_instant() -> None:
    at = datetime(2026, 5, 26, 14, 30, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert (
        format_prompt_clock(timezone_name="Asia/Shanghai", at=at)
        == "2026年5月26日 星期二 14:30:05 (Asia/Shanghai)"
    )


def test_build_prompt_clock_context_prefix() -> None:
    at = datetime(2026, 1, 1, 9, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    line = build_prompt_clock_context(timezone_name="Asia/Shanghai", at=at)
    assert line.startswith("当前参考时间: 2026年1月1日")


def test_resolve_prompt_timezone_falls_back_on_invalid() -> None:
    class _Settings:
        sql_agent_prompt_timezone = "Not/A/Timezone"

    assert resolve_prompt_timezone(_Settings()) == "Asia/Shanghai"
