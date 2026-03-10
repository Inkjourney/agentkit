"""Helpers for working with provider usage accounting."""

from __future__ import annotations

from typing import Any, Mapping

from agentkit.llm.types import Usage


def merge_usage(total: Usage, delta: Usage) -> None:
    """Accumulate one usage snapshot into another in place."""

    total.input_tokens = _sum_optional_int(total.input_tokens, delta.input_tokens)
    total.output_tokens = _sum_optional_int(total.output_tokens, delta.output_tokens)
    total.reasoning_tokens = _sum_optional_int(
        total.reasoning_tokens, delta.reasoning_tokens
    )
    total.cache_read_tokens = _sum_optional_int(
        total.cache_read_tokens, delta.cache_read_tokens
    )
    total.cache_write_tokens = _sum_optional_int(
        total.cache_write_tokens, delta.cache_write_tokens
    )

    delta_total = delta.total_tokens
    if delta_total is None and delta.input_tokens is not None and delta.output_tokens is not None:
        delta_total = delta.input_tokens + delta.output_tokens
    total.total_tokens = _sum_optional_int(total.total_tokens, delta_total)
    total.raw = None


def usage_to_payload(usage: Usage) -> dict[str, int | None]:
    """Serialize usage into the run-log friendly payload shape."""
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
    }


def usage_from_payload(payload: Mapping[str, Any]) -> Usage:
    """Rebuild a :class:`Usage` object from serialized run-log data."""
    return Usage(
        input_tokens=_optional_int(payload.get("input_tokens")),
        output_tokens=_optional_int(payload.get("output_tokens")),
        total_tokens=_optional_int(payload.get("total_tokens")),
        reasoning_tokens=_optional_int(payload.get("reasoning_tokens")),
        cache_read_tokens=_optional_int(payload.get("cache_read_tokens")),
        cache_write_tokens=_optional_int(payload.get("cache_write_tokens")),
    )


def _sum_optional_int(current: int | None, delta: int | None) -> int | None:
    """Add two optional counters while preserving ``None`` as unknown."""
    if delta is None:
        return current
    if current is None:
        return delta
    return current + delta


def _optional_int(value: Any) -> int | None:
    """Best-effort convert provider payload values into integers."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
