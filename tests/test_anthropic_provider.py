from __future__ import annotations

from typing import Any

import pytest

from agentkit.config.schema import ProviderConfig
from agentkit.errors import ProviderError
from agentkit.llm.factory import build_provider
from agentkit.llm.types import (
    ConversationState,
    GenerationOptions,
    MessageItem,
    ToolCallItem,
    ToolResultItem,
    UnifiedLLMRequest,
    UnifiedToolSpec,
)


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = FakeResponse(200, {})

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    fake = FakeSession()
    monkeypatch.setattr(
        "agentkit.llm.providers.anthropic_provider.requests.Session", lambda: fake
    )
    return fake


def _req() -> UnifiedLLMRequest:
    return UnifiedLLMRequest(
        provider="anthropic",
        model="claude-test",
        state=ConversationState(
            history=[
                MessageItem(role="user", text="history user"),
                ToolCallItem(call_id="call-0", name="echo", arguments={"text": "x"}),
                ToolResultItem(
                    call_id="call-0",
                    tool_name="echo",
                    payload={"output": {"echo": "x"}},
                ),
            ]
        ),
        inputs=[MessageItem(role="user", text="new input")],
        instructions="be strict",
        tools=[
            UnifiedToolSpec(
                name="echo",
                description="Echo",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ],
        options=GenerationOptions(max_output_tokens=512, temperature=0.2),
    )


def test_anthropic_compile_and_parse_tool_use_loop(fake_session: FakeSession) -> None:
    provider = build_provider(
        ProviderConfig(kind="anthropic", model="claude-test", api_key="test-key")
    )
    fake_session.response = FakeResponse(
        200,
        {
            "id": "msg_1",
            "stop_reason": "tool_use",
            "content": [
                {"type": "thinking", "thinking": "internal thought"},
                {"type": "text", "text": "I need a tool"},
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "echo",
                    "input": {"text": "hello"},
                },
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 6,
                "cache_creation_input_tokens": 2,
                "cache_read_input_tokens": 1,
            },
        },
    )

    response = provider.generate(_req())

    payload = fake_session.calls[0]["json"]
    assert payload["system"] == "be strict"
    assert payload["model"] == "claude-test"
    assert payload["max_tokens"] == 512
    assert payload["tools"][0]["name"] == "echo"

    roles = [message["role"] for message in payload["messages"]]
    assert roles == ["user", "assistant", "user"]

    assert response.status == "requires_tool"
    assert response.reason == "tool_call"
    assert response.output_text == "I need a tool"
    assert response.tool_calls[0].name == "echo"
    assert response.usage.input_tokens == 10
    assert response.usage.cache_write_tokens == 2


def test_anthropic_stop_reason_mapping_and_errors(fake_session: FakeSession) -> None:
    provider = build_provider(ProviderConfig(kind="anthropic", api_key="test-key"))

    assert provider._map_status({"stop_reason": "end_turn"}, []) == ("completed", "stop")
    assert provider._map_status({"stop_reason": "max_tokens"}, []) == (
        "incomplete",
        "max_tokens",
    )
    assert provider._map_status({"stop_reason": "refusal"}, []) == ("blocked", "refusal")

    fake_session.response = FakeResponse(401, {"error": {"type": "invalid_api_key"}})
    with pytest.raises(ProviderError, match="status 401"):
        provider.generate(_req())


def test_anthropic_compiles_string_tool_result_content(fake_session: FakeSession) -> None:
    provider = build_provider(ProviderConfig(kind="anthropic", api_key="test-key"))
    req = UnifiedLLMRequest(
        provider="anthropic",
        model="claude-test",
        state=ConversationState(
            history=[
                ToolResultItem(
                    call_id="call-1",
                    tool_name="str_replace",
                    payload="The file draft.txt has been edited.",
                )
            ]
        ),
        inputs=[],
        instructions="",
        tools=[],
        options=GenerationOptions(),
    )

    messages = provider._compile_messages(req.state.history)

    assert messages == [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "content": "The file draft.txt has been edited.",
                    "is_error": False,
                }
            ],
        }
    ]
