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
    monkeypatch.setattr("agentkit.llm.providers.gemini_provider.requests.Session", lambda: fake)
    return fake


def _req() -> UnifiedLLMRequest:
    return UnifiedLLMRequest(
        provider="gemini",
        model="gemini-2.0-flash",
        state=ConversationState(
            history=[
                ToolCallItem(call_id="call-0", name="echo", arguments={"text": "x"}),
                ToolResultItem(
                    call_id="call-0",
                    tool_name="echo",
                    payload={"output": {"echo": "x"}},
                ),
            ],
            provider_meta={"tool_name_by_call_id": {"call-0": "echo"}},
        ),
        inputs=[MessageItem(role="user", text="hello")],
        instructions="be brief",
        tools=[
            UnifiedToolSpec(
                name="echo",
                description="Echo",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ],
        options=GenerationOptions(max_output_tokens=128, temperature=0.3),
    )


def test_gemini_compile_and_parse_function_calls(fake_session: FakeSession) -> None:
    provider = build_provider(
        ProviderConfig(kind="gemini", model="gemini-2.0-flash", api_key="test-key")
    )
    fake_session.response = FakeResponse(
        200,
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"text": "let me call tool"},
                            {
                                "functionCall": {
                                    "id": "fc-1",
                                    "name": "echo",
                                    "args": {"text": "hello"},
                                }
                            },
                        ]
                    },
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 8,
                "totalTokenCount": 19,
                "thoughtsTokenCount": 2,
                "cachedContentTokenCount": 1,
            },
        },
    )

    response = provider.generate(_req())

    payload = fake_session.calls[0]["json"]
    assert payload["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert payload["generationConfig"]["maxOutputTokens"] == 128
    assert payload["tools"][0]["functionDeclarations"][0]["name"] == "echo"

    # history tool_result should be compiled to functionResponse
    flattened_parts = [part for content in payload["contents"] for part in content["parts"]]
    assert any("functionResponse" in part for part in flattened_parts)

    assert response.status == "requires_tool"
    assert response.reason == "tool_call"
    assert response.output_text == "let me call tool"
    assert response.tool_calls[0].call_id == "fc-1"
    assert response.usage.reasoning_tokens == 2
    assert response.state_patch.provider_meta_patch["tool_name_by_call_id"] == {"fc-1": "echo"}


def test_gemini_prompt_feedback_blocked(fake_session: FakeSession) -> None:
    provider = build_provider(ProviderConfig(kind="gemini", api_key="test-key"))
    fake_session.response = FakeResponse(
        200,
        {
            "promptFeedback": {"blockReason": "SAFETY"},
            "candidates": [],
            "usageMetadata": {"promptTokenCount": 3, "totalTokenCount": 3},
        },
    )

    response = provider.generate(_req())

    assert response.status == "blocked"
    assert response.reason == "content_filter"
    assert response.output_items == []


def test_gemini_finish_reason_mapping_and_http_error(fake_session: FakeSession) -> None:
    provider = build_provider(ProviderConfig(kind="gemini", api_key="test-key"))

    assert provider._map_status({"finishReason": "STOP"}, []) == ("completed", "stop")
    assert provider._map_status({"finishReason": "MAX_TOKENS"}, []) == (
        "incomplete",
        "max_tokens",
    )
    assert provider._map_status({"finishReason": "SAFETY"}, []) == (
        "blocked",
        "content_filter",
    )

    fake_session.response = FakeResponse(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
    with pytest.raises(ProviderError, match="status 429"):
        provider.generate(_req())


def test_gemini_wraps_string_tool_result_in_function_response(fake_session: FakeSession) -> None:
    provider = build_provider(ProviderConfig(kind="gemini", api_key="test-key"))
    req = UnifiedLLMRequest(
        provider="gemini",
        model="gemini-2.0-flash",
        state=ConversationState(
            history=[
                ToolResultItem(
                    call_id="call-raw",
                    tool_name="str_replace",
                    payload="The file draft.txt has been edited.",
                )
            ],
            provider_meta={"tool_name_by_call_id": {"call-raw": "str_replace"}},
        ),
        inputs=[],
        instructions="",
        tools=[],
        options=GenerationOptions(),
    )

    contents = provider._compile_contents(req.state.history, req)

    assert contents == [
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "str_replace",
                        "response": {
                            "content": "The file draft.txt has been edited.",
                            "call_id": "call-raw",
                            "tool_name": "str_replace",
                        },
                    }
                }
            ],
        }
    ]
