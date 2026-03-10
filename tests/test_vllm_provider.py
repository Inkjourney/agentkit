from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agentkit.config.provider_defaults import DEFAULT_VLLM_BASE_URL
from agentkit.config.schema import ProviderConfig
from agentkit.llm.factory import build_provider
from agentkit.llm.types import (
    ConversationState,
    GenerationOptions,
    MessageItem,
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


def test_vllm_provider_sends_enable_thinking_without_reasoning_effort(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = build_provider(
        ProviderConfig(
            kind="vllm",
            model="qwen3",
            openai_api_variant="chat_completions",
            base_url=DEFAULT_VLLM_BASE_URL,
            enable_thinking=True,
        )
    )

    instance = fake_openai.instances[-1]
    instance.chat.completions.result = {
        "id": "chat-1",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": "hello",
                },
            }
        ],
    }

    req = UnifiedLLMRequest(
        provider="vllm",
        model="qwen3",
        state=ConversationState(),
        inputs=[MessageItem(role="user", text="hi")],
        instructions="",
        tools=[],
        options=GenerationOptions(reasoning_effort="high", thinking_enabled=False),
    )

    response = provider.generate(req)

    assert provider.config.base_url == DEFAULT_VLLM_BASE_URL
    assert provider.config.api_key is None
    assert instance.kwargs["base_url"] == DEFAULT_VLLM_BASE_URL
    assert instance.kwargs["api_key"] == "empty"
    kwargs = instance.chat.completions.calls[0]
    assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert "reasoning_effort" not in kwargs

    assert response.provider_name == "vllm"
    assert response.status == "completed"
    assert response.reason == "stop"
