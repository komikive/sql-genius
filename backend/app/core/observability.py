"""Optional Langfuse tracing with content capture disabled by default."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager, nullcontext
from functools import lru_cache, wraps
from typing import Any, Callable, Iterator, TypeVar

from langfuse import Langfuse, propagate_attributes

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|authorization|password|secret|token)", re.I)
_URL_CREDENTIAL_RE = re.compile(r"(://[^:@/\s]+:)([^@/\s]+)(@)")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_F = TypeVar("_F", bound=Callable[..., Any])


def redact_trace_value(value: Any) -> Any:
    """Redact common credentials from explicitly captured trace content."""
    if isinstance(value, str):
        masked = _URL_CREDENTIAL_RE.sub(r"\1***\3", value)
        return _BEARER_RE.sub(r"\1***", masked)
    if isinstance(value, dict):
        return {
            str(key): "***" if _SECRET_KEY_RE.search(str(key)) else redact_trace_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_trace_value(item) for item in value]
    return value


def trace_content(value: Any, *, fallback: Any | None = None) -> Any | None:
    """Return redacted content when opted in, otherwise a non-sensitive summary."""
    if not get_settings().sql_agent_observability_capture_content:
        return fallback
    return redact_trace_value(value)


@lru_cache(maxsize=1)
def get_langfuse_client() -> Langfuse | None:
    settings = get_settings()
    if not settings.sql_agent_observability_enabled:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
            environment=settings.sql_agent_env,
            sample_rate=settings.sql_agent_observability_sample_rate,
        )
    except Exception:
        logger.exception("Langfuse initialization failed; tracing is disabled")
        return None


@contextmanager
def trace_observation(
    name: str,
    *,
    as_type: str = "span",
    input: Any | None = None,
    input_summary: Any | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
) -> Iterator[Any | None]:
    """Create one observation when Langfuse is configured; otherwise no-op."""
    client = get_langfuse_client()
    if client is None:
        with nullcontext(None) as observation:
            yield observation
        return

    with client.start_as_current_observation(
        name=name,
        as_type=as_type,
        input=trace_content(input, fallback=input_summary),
        metadata=metadata,
        model=model,
    ) as observation:
        try:
            yield observation
        except Exception as exc:
            observation.update(level="ERROR", status_message=type(exc).__name__)
            raise


def traced(name: str, *, as_type: str = "span") -> Callable[[_F], _F]:
    """Trace an async function without exporting its arguments or return value."""
    def decorator(func: _F) -> _F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_observation(name, as_type=as_type) as observation:
                result = await func(*args, **kwargs)
                if observation is not None:
                    observation.update(output={"status": "completed"})
                return result

        return wrapper  # type: ignore[return-value]

    return decorator


def trace_attributes(
    *,
    thread_id: str,
    datasource_id: str | None,
) -> Any:
    """Attach safe request-scoped dimensions to the current trace and children."""
    if get_langfuse_client() is None:
        return nullcontext()
    metadata = {"datasource_id": datasource_id} if datasource_id else {}
    return propagate_attributes(
        session_id=thread_id[:200],
        trace_name="sql-genius-chat",
        tags=["sql-genius", "langgraph"],
        metadata=metadata,
        environment=get_settings().sql_agent_env,
    )


def shutdown_langfuse() -> None:
    """Flush queued events and stop the SDK worker during app shutdown."""
    client = get_langfuse_client()
    if client is not None:
        try:
            client.shutdown()
        except Exception:
            logger.exception("Langfuse shutdown failed")


def usage_details_from_message(message: Any) -> dict[str, int] | None:
    """Normalize LangChain/OpenAI token usage for Langfuse generations."""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        mapped = {
            "input": int(usage.get("input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0),
            "total": int(usage.get("total_tokens") or 0),
        }
        return {key: value for key, value in mapped.items() if value > 0} or None

    response_metadata = getattr(message, "response_metadata", None)
    token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
    if isinstance(token_usage, dict):
        mapped = {
            "input": int(token_usage.get("prompt_tokens") or 0),
            "output": int(token_usage.get("completion_tokens") or 0),
            "total": int(token_usage.get("total_tokens") or 0),
        }
        return {key: value for key, value in mapped.items() if value > 0} or None
    return None
