"""Helpers for extracting structured JSON outputs from chat model responses."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def content_to_text(content: Any) -> str:
    """Normalize provider content blocks into plain text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part).strip()
    return str(content).strip()


def candidate_json_strings(text: str) -> list[str]:
    """Return plausible JSON substrings from raw model output."""
    candidates: list[str] = []
    cleaned = text.strip()
    if cleaned:
        candidates.append(cleaned)

    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in fenced:
        block = block.strip()
        if block:
            candidates.append(block)

    brace_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if brace_match:
        block = brace_match.group(0).strip()
        if block:
            candidates.append(block)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def parse_model_output(model_cls: type[ModelT], raw_text: str) -> ModelT:
    """Parse raw model text into a Pydantic model using a few safe fallbacks."""
    last_error: ValidationError | None = None
    for candidate in candidate_json_strings(raw_text):
        try:
            return model_cls.model_validate_json(candidate)
        except ValidationError as exc:
            last_error = exc
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            try:
                return model_cls.model_validate(parsed)
            except ValidationError as inner_exc:
                last_error = inner_exc
                continue

    if last_error is not None:
        raise last_error
    raise ValidationError.from_exception_data(
        model_cls.__name__,
        [
            {
                "type": "missing",
                "loc": ("root",),
                "msg": "Could not parse model output into the target schema",
                "input": raw_text,
            }
        ],
    )
