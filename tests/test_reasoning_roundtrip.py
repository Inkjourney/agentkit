from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agentkit.config.schema import ProviderConfig
from agentkit.llm.factory import build_provider
from agentkit.llm.providers.openai_provider import OpenAIProvider
from agentkit.llm.types import (
    ConversationState,
    GenerationOptions,
    MessageItem,
    ReasoningItem,
    UnifiedLLMRequest,
)


class FakeEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result: Any = None

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.result


class FakeOpenAI:
    instances: list["FakeOpenAI"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.responses = FakeEndpoint()
        self.chat = SimpleNamespace(completions=FakeEndpoint())
        FakeOpenAI.instances.append(self)


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> type[FakeOpenAI]:
    FakeOpenAI.instances = []
    monkeypatch.setattr("agentkit.llm.providers.openai_provider.OpenAI", FakeOpenAI)
    return FakeOpenAI


def test_openai_reasoning_saved_and_replayed_on_same_provider(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(ProviderConfig(kind="openai", openai_api_variant="responses"))

    parsed = provider._parse_responses_response(
        {
            "id": "resp-1",
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": [{"text": "trace"}]},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hello"}],
                },
            ],
        }
    )

    reasoning = next(item for item in parsed.output_items if isinstance(item, ReasoningItem))
    assert reasoning.raw_item is not None

    instance = fake_openai.instances[-1]
    instance.responses.result = {
        "id": "resp-2",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            }
        ],
    }

    req = UnifiedLLMRequest(
        provider="openai",
        model="gpt-5",
        state=ConversationState(history=[reasoning]),
        inputs=[MessageItem(role="user", text="next turn")],
        instructions="",
        tools=[],
        options=GenerationOptions(),
    )
    provider.generate(req)

    sent_input = instance.responses.calls[0]["input"]
    assert sent_input[0]["type"] == "reasoning"
    assert sent_input[1] == {"role": "user", "content": "next turn"}


def test_reasoning_not_replayed_cross_provider() -> None:
    gemini = build_provider(ProviderConfig(kind="gemini", api_key="test-key"))
    openai_reasoning = ReasoningItem(
        text=None,
        summary="trace",
        raw_item={"type": "reasoning", "summary": [{"text": "trace"}]},
        replay_hint=True,
    )

    req = UnifiedLLMRequest(
        provider="gemini",
        model="gemini-2.0",
        state=ConversationState(),
        inputs=[MessageItem(role="user", text="hello")],
        instructions="",
        tools=[],
        options=GenerationOptions(),
    )

    contents = gemini._compile_contents([openai_reasoning] + req.inputs, req)
    flattened_parts = [part for content in contents for part in content["parts"]]

    assert all("thoughtSignature" not in part for part in flattened_parts)
    assert len(flattened_parts) == 1
    assert flattened_parts[0]["text"] == "hello"
