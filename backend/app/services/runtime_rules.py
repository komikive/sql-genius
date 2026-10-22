"""Helpers for datasource-scoped runtime rules in the skill-only flow."""

from __future__ import annotations

from typing import Any

from app.db.models.datasource_profile import DatasourceProfile

__all__ = [
    "merge_profile_runtime_rules",
]


def _extract_rule_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, dict):
        for key in ("body", "rule", "text", "content"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _normalize_rule_entry(value: Any) -> dict[str, Any] | None:
    body = _extract_rule_text(value)
    if body is None:
        return None
    title = "运行时规则"
    scope = "datasource"
    source = "profile"
    metadata: dict[str, Any] = {}
    if isinstance(value, dict):
        raw_title = value.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            title = raw_title.strip()
        raw_scope = value.get("scope")
        if isinstance(raw_scope, str) and raw_scope.strip():
            scope = raw_scope.strip()
        raw_source = value.get("source")
        if isinstance(raw_source, str) and raw_source.strip():
            source = raw_source.strip()
        metadata = {
            key: item
            for key, item in value.items()
            if key not in {"title", "body", "rule", "text", "content", "scope", "source"}
        }
    return {
        "title": title,
        "body": body,
        "scope": scope,
        "source": source,
        **metadata,
    }


def _dedupe_rule_entries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_rule_entry(item)
        if normalized is None or normalized["body"] in seen:
            continue
        seen.add(normalized["body"])
        deduped.append(normalized)
    return deduped


def _list_profile_runtime_rules_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_rules = payload.get("runtime_rules")
    if not isinstance(raw_rules, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw_rules:
        entry = _normalize_rule_entry(item)
        if entry is not None:
            normalized.append(entry)
    return _dedupe_rule_entries(normalized)


def merge_profile_runtime_rules(
    existing_profile_json: dict[str, Any] | None,
    next_profile_json: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(next_profile_json or {})
    combined = _dedupe_rule_entries(
        [
            *_list_profile_runtime_rules_from_payload(existing_profile_json),
            *_list_profile_runtime_rules_from_payload(next_profile_json),
        ]
    )
    if combined:
        merged["runtime_rules"] = combined
    else:
        merged.pop("runtime_rules", None)
    return merged
