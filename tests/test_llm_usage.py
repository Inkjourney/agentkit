from __future__ import annotations

from agentkit.llm.types import Usage
from agentkit.llm.usage import merge_usage, usage_from_payload, usage_to_payload


def test_merge_usage_accumulates_optional_fields_and_derived_total() -> None:
    total = Usage(
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        reasoning_tokens=2,
        cache_read_tokens=1,
        raw={"provider": "openai"},
    )

    merge_usage(
        total,
        Usage(
            input_tokens=7,
            output_tokens=3,
            reasoning_tokens=1,
            cache_write_tokens=5,
            raw={"provider": "openai"},
        ),
    )

    assert total.input_tokens == 17
    assert total.output_tokens == 7
    assert total.total_tokens == 24
    assert total.reasoning_tokens == 3
    assert total.cache_read_tokens == 1
    assert total.cache_write_tokens == 5
    assert total.raw is None


def test_usage_payload_round_trip_coerces_int_like_values() -> None:
    payload = {
        "input_tokens": "12",
        "output_tokens": 5,
        "total_tokens": "17",
        "reasoning_tokens": None,
        "cache_read_tokens": "2",
        "cache_write_tokens": "bad",
    }

    usage = usage_from_payload(payload)

    assert usage == Usage(
        input_tokens=12,
        output_tokens=5,
        total_tokens=17,
        reasoning_tokens=None,
        cache_read_tokens=2,
        cache_write_tokens=None,
    )
    assert usage_to_payload(usage) == {
        "input_tokens": 12,
        "output_tokens": 5,
        "total_tokens": 17,
        "reasoning_tokens": None,
        "cache_read_tokens": 2,
        "cache_write_tokens": None,
    }
