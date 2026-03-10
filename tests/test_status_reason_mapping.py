from __future__ import annotations

from agentkit.config.schema import ProviderConfig
from agentkit.llm.factory import build_provider
from agentkit.llm.providers.openai_provider import OpenAIProvider
from agentkit.llm.types import ToolCallItem


def test_status_reason_requires_tool_when_tool_calls_exist() -> None:
    openai = OpenAIProvider(
        ProviderConfig(kind="openai", openai_api_variant="responses", api_key="test")
    )
    status, reason = openai._map_responses_status(
        {"status": "completed"},
        [ToolCallItem(call_id="c1", name="echo", arguments={})],
        saw_refusal=False,
    )
    assert status == "requires_tool"
    assert reason == "tool_call"


def test_status_reason_completed_and_incomplete_and_blocked() -> None:
    openai = OpenAIProvider(
        ProviderConfig(kind="openai", openai_api_variant="chat_completions", api_key="test")
    )

    assert openai._map_chat_status(
        finish_reason="stop",
        output_items=[],
        saw_refusal=False,
    ) == ("completed", "stop")

    assert openai._map_chat_status(
        finish_reason="length",
        output_items=[],
        saw_refusal=False,
    ) == ("incomplete", "max_tokens")

    assert openai._map_chat_status(
        finish_reason="content_filter",
        output_items=[],
        saw_refusal=False,
    ) == ("blocked", "content_filter")

    assert openai._map_chat_status(
        finish_reason="stop",
        output_items=[],
        saw_refusal=True,
    ) == ("blocked", "refusal")


def test_status_reason_context_pause_failed_unknown() -> None:
    openai = OpenAIProvider(
        ProviderConfig(kind="openai", openai_api_variant="responses", api_key="test")
    )

    assert openai._map_responses_status(
        {"status": "incomplete", "incomplete_details": {"reason": "context_window_exceeded"}},
        [],
        saw_refusal=False,
    ) == ("incomplete", "context_window")

    assert openai._map_responses_status(
        {"status": "incomplete", "incomplete_details": {"reason": "pause_turn"}},
        [],
        saw_refusal=False,
    ) == ("incomplete", "pause")

    assert openai._map_responses_status(
        {"status": "failed"},
        [],
        saw_refusal=False,
    ) == ("failed", "error")

    assert openai._map_responses_status(
        {"status": "incomplete", "incomplete_details": {"reason": "something_new"}},
        [],
        saw_refusal=False,
    ) == ("incomplete", "unknown")


def test_status_reason_anthropic_and_gemini_mappings() -> None:
    anthropic = build_provider(ProviderConfig(kind="anthropic", api_key="test-key"))
    gemini = build_provider(ProviderConfig(kind="gemini", api_key="test-key"))

    assert anthropic._map_status({"stop_reason": "model_context_window_exceeded"}, []) == (
        "incomplete",
        "context_window",
    )
    assert anthropic._map_status({"stop_reason": "refusal"}, []) == (
        "blocked",
        "refusal",
    )

    assert gemini._map_status({"finishReason": "MAX_TOKENS"}, []) == (
        "incomplete",
        "max_tokens",
    )
    assert gemini._map_status({"finishReason": "RECITATION"}, []) == (
        "blocked",
        "content_filter",
    )
