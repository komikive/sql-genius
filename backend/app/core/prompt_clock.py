"""为 Agent 系统提示注入墙钟时间（「今天」「近30天」等相对时间换算基准）。

配置：SQL_AGENT_PROMPT_TIMEZONE，默认 Asia/Shanghai。
由 autonomous_agent._build_system_message 在每轮 LLM 调用前刷新。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import Settings

DEFAULT_PROMPT_TIMEZONE = "Asia/Shanghai"

_WEEKDAY_ZH = (
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
)


def resolve_prompt_timezone(settings: Settings | None = None) -> str:
    """Return a valid IANA timezone name for prompt injection."""
    raw = DEFAULT_PROMPT_TIMEZONE
    if settings is not None:
        configured = str(getattr(settings, "sql_agent_prompt_timezone", "") or "").strip()
        if configured:
            raw = configured
    try:
        ZoneInfo(raw)
    except Exception:
        return DEFAULT_PROMPT_TIMEZONE
    return raw


def format_prompt_clock(
    *,
    timezone_name: str = DEFAULT_PROMPT_TIMEZONE,
    at: datetime | None = None,
) -> str:
    """Human-readable timestamp for model context, e.g. 2026年5月26日 星期二 14:30:05 (Asia/Shanghai)."""
    tz_name = timezone_name
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = DEFAULT_PROMPT_TIMEZONE
        tz = ZoneInfo(tz_name)

    if at is None:
        now = datetime.now(tz)
    else:
        now = at.astimezone(tz) if at.tzinfo is not None else at.replace(tzinfo=tz)

    weekday = _WEEKDAY_ZH[now.weekday()]
    return (
        f"{now.year}年{now.month}月{now.day}日 {weekday} "
        f"{now.hour:02d}:{now.minute:02d}:{now.second:02d} ({tz_name})"
    )


def build_prompt_clock_context(
    *,
    settings: Settings | None = None,
    timezone_name: str | None = None,
    at: datetime | None = None,
) -> str:
    """Single-line clock context for HumanMessage / system prompt blocks."""
    tz = timezone_name or resolve_prompt_timezone(settings)
    return f"当前参考时间: {format_prompt_clock(timezone_name=tz, at=at)}"
