from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agentkit.config.provider_defaults import DEFAULT_QWEN_BASE_URL
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


def test_qwen_provider_defaults_and_extra_body(fake_openai: type[FakeOpenAI]) -> None:
    provider = build_provider(
        ProviderConfig(
            kind="qwen",
            model="qwen3-max",
            openai_api_variant="chat_completions",
            base_url=DEFAULT_QWEN_BASE_URL,
            thinking_budget=2048,
            enable_thinking=True,
        )
    )

    instance = fake_openai.instances[-1]
    instance.chat.completions.result = {
        "id": "chat-1",
        "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
    }

    req = UnifiedLLMRequest(
        provider="qwen",
        model="qwen3-max",
        state=ConversationState(),
        inputs=[MessageItem(role="user", text="hi")],
        instructions="sys",
        tools=[],
        options=GenerationOptions(thinking_enabled=False),
    )

    response = provider.generate(req)

    assert provider.config.base_url == DEFAULT_QWEN_BASE_URL
    kwargs = instance.chat.completions.calls[0]
    assert kwargs["extra_body"] == {
        "enable_thinking": False,
        "thinking_budget": 2048,
    }
    assert response.provider_name == "qwen"
    assert response.status == "completed"
