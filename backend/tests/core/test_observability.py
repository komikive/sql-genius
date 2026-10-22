from app.core.config import get_settings
from app.core.observability import (
    get_langfuse_client,
    redact_trace_value,
    trace_content,
    trace_observation,
    usage_details_from_message,
)


def test_redact_trace_value_masks_credentials_recursively() -> None:
    value = {
        "database_url": "postgresql://user:secret@db:5432/app",
        "authorization": "Bearer abc.def",
        "nested": ["Bearer token-123"],
    }

    masked = redact_trace_value(value)

    assert "secret" not in str(masked)
    assert "abc.def" not in str(masked)
    assert "token-123" not in str(masked)
    assert "***" in str(masked)


def test_trace_content_uses_safe_summary_when_capture_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SQL_AGENT_OBSERVABILITY_CAPTURE_CONTENT", "0")
    get_settings.cache_clear()
    try:
        assert trace_content(
            {"sql": "SELECT secret FROM users"},
            fallback={"sql_chars": 24},
        ) == {"sql_chars": 24}
    finally:
        get_settings.cache_clear()


def test_observability_is_a_noop_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SQL_AGENT_OBSERVABILITY_ENABLED", "0")
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()
    try:
        with trace_observation("disabled") as observation:
            assert observation is None
    finally:
        get_settings.cache_clear()
        get_langfuse_client.cache_clear()


def test_usage_details_from_message_normalizes_langchain_usage() -> None:
    message = type(
        "Message",
        (),
        {"usage_metadata": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}},
    )()

    assert usage_details_from_message(message) == {
        "input": 12,
        "output": 8,
        "total": 20,
    }
