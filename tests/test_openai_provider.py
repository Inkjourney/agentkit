from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agentkit.config.schema import ProviderConfig
from agentkit.errors import ProviderError
from agentkit.llm.providers.openai_provider import OpenAIProvider
from agentkit.llm.types import (
    ConversationState,
    GenerationOptions,
    MessageItem,
    ToolCallItem,
    ToolResultItem,
    UnifiedLLMRequest,
    UnifiedToolSpec,
)


class FakeEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result: Any = None
        self.error: Exception | None = None

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
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


def _base_req(*, model: str = "gpt-test") -> UnifiedLLMRequest:
    return UnifiedLLMRequest(
        provider="openai",
        model=model,
        state=ConversationState(),
        inputs=[MessageItem(role="user", text="hello")],
        instructions="sys",
        tools=[
            UnifiedToolSpec(
                name="echo",
                description="Echo",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ],
        options=GenerationOptions(temperature=0.4, reasoning_effort="medium"),
    )


def test_openai_provider_initializes_client_kwargs(fake_openai: type[FakeOpenAI]) -> None:
    provider = OpenAIProvider(
        ProviderConfig(
            model="test-model",
            timeout_s=12,
            retries=3,
            api_key="secret",
            base_url="https://example.invalid",
            openai_api_variant="responses",
        )
    )
    instance = fake_openai.instances[-1]

    assert provider.model == "test-model"
    assert instance.kwargs == {
        "timeout": 12,
        "max_retries": 3,
        "api_key": "secret",
        "base_url": "https://example.invalid",
    }


def test_generate_responses_server_cursor_and_parse_output_items(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(
        ProviderConfig(
            openai_api_variant="responses",
            model="gpt-test",
        )
    )
    instance = fake_openai.instances[-1]
    instance.responses.result = {
        "id": "resp-2",
        "status": "completed",
        "incomplete_details": None,
        "output": [
            {
                "type": "reasoning",
                "summary": [{"text": "analysis summary"}],
            },
            {
                "type": "function_call",
                "id": "fc-1",
                "call_id": "call-1",
                "name": "echo",
                "arguments": '{"text":"hi"}',
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hello from model"}],
            },
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "output_tokens_details": {"reasoning_tokens": 2},
            "input_tokens_details": {"cached_tokens": 3},
        },
    }

    req = _base_req()
    req.state.mode = "auto"
    req.state.provider_cursor = "resp-1"
    req.state.history = [MessageItem(role="user", text="old history")]

    response = provider.generate(req)

    request_kwargs = instance.responses.calls[0]
    assert request_kwargs["model"] == "gpt-test"
    assert request_kwargs["previous_response_id"] == "resp-1"
    # server cursor mode: only current inputs are sent
    assert request_kwargs["input"] == [{"role": "user", "content": "hello"}]
    assert request_kwargs["instructions"] == "sys"

    assert response.response_id == "resp-2"
    assert response.status == "requires_tool"
    assert response.reason == "tool_call"
    assert response.output_text == "hello from model"
    assert response.state_patch.new_provider_cursor == "resp-2"
    assert len(response.output_items) == 3
    assert response.tool_calls[0].name == "echo"
    assert response.usage.reasoning_tokens == 2
    assert response.usage.cache_read_tokens == 3


def test_generate_chat_completions_builds_messages_and_maps_status(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(
        ProviderConfig(
            openai_api_variant="chat_completions",
            reasoning_effort="high",
            model="chat-model",
        )
    )
    instance = fake_openai.instances[-1]
    instance.chat.completions.result = {
        "id": "chat-1",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": "assistant reply",
                    "tool_calls": [
                        {
                            "type": "function",
                            "id": "call-1",
                            "function": {
                                "name": "echo",
                                "arguments": '{"text":"hello"}',
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 7,
            "completion_tokens": 9,
            "total_tokens": 16,
            "completion_tokens_details": {"reasoning_tokens": 4},
        },
    }

    req = _base_req(model="chat-model")
    req.state.history = [
        ToolCallItem(call_id="call-0", name="echo", arguments={"text": "x"}),
        ToolResultItem(
            call_id="call-0",
            tool_name="echo",
            payload={"output": {"echo": "x"}},
        ),
    ]
    req.instructions = "sys\ndev"

    response = provider.generate(req)

    request_kwargs = instance.chat.completions.calls[0]
    assert request_kwargs["model"] == "chat-model"
    assert request_kwargs["messages"][0] == {"role": "system", "content": "sys\ndev"}
    assert request_kwargs["messages"][1]["role"] == "assistant"
    assert request_kwargs["messages"][2] == {
        "role": "tool",
        "tool_call_id": "call-0",
        "content": '{"output": {"echo": "x"}}',
    }
    assert request_kwargs["reasoning_effort"] == "medium"

    assert response.status == "requires_tool"
    assert response.reason == "tool_call"
    assert response.output_text == "assistant reply"
    assert response.tool_calls[0].call_id == "call-1"
    assert response.usage.reasoning_tokens == 4


def test_chat_roundtrip_restores_glm_style_assistant_message(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(
        ProviderConfig(openai_api_variant="chat_completions", model="glm-5")
    )
    parsed = provider._parse_chat_response(
        {
            "id": "chatcmpl-1",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "我来帮你判断这两个数是否是质数。",
                        "reasoning": "先调用 is_prime，再根据结果决定 factorize。",
                        "tool_calls": [
                            {
                                "id": "chatcmpl-tool-a",
                                "type": "function",
                                "function": {
                                    "name": "is_prime",
                                    "arguments": '{"n": 1121}',
                                },
                            },
                            {
                                "id": "chatcmpl-tool-b",
                                "type": "function",
                                "function": {
                                    "name": "is_prime",
                                    "arguments": '{"n": 1231}',
                                },
                            },
                        ],
                    },
                }
            ],
        }
    )

    req = UnifiedLLMRequest(
        provider="openai",
        model="glm-5",
        state=ConversationState(
            history=[
                MessageItem(role="user", text="判断 1121 和 1231 是否质数"),
                *parsed.output_items,
                ToolResultItem(
                    call_id="chatcmpl-tool-a",
                    tool_name="is_prime",
                    payload={"n": 1121, "is_prime": False},
                ),
                ToolResultItem(
                    call_id="chatcmpl-tool-b",
                    tool_name="is_prime",
                    payload={"n": 1231, "is_prime": True},
                ),
            ]
        ),
        inputs=[],
        instructions="",
        tools=[],
        options=GenerationOptions(),
    )
    compiled = provider._compile_chat_messages(req.state.history, req)

    assert compiled[0] == {"role": "user", "content": "判断 1121 和 1231 是否质数"}
    assert compiled[1]["role"] == "assistant"
    assert compiled[1]["content"] == "我来帮你判断这两个数是否是质数。"
    assert compiled[1]["reasoning"] == "先调用 is_prime，再根据结果决定 factorize。"
    assert [call["id"] for call in compiled[1]["tool_calls"]] == [
        "chatcmpl-tool-a",
        "chatcmpl-tool-b",
    ]
    assert [call["function"]["arguments"] for call in compiled[1]["tool_calls"]] == [
        '{"n": 1121}',
        '{"n": 1231}',
    ]
    assert compiled[2]["role"] == "tool"
    assert compiled[3]["role"] == "tool"


def test_openai_serialize_tool_result_keeps_string_payload_unwrapped(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(ProviderConfig(api_key="secret"))
    item = ToolResultItem(
        call_id="call-raw",
        tool_name="str_replace",
        payload="The file draft.txt has been edited.",
    )

    assert provider._serialize_tool_result(item) == "The file draft.txt has been edited."


def test_chat_roundtrip_restores_qwen_reasoning_content_and_empty_content(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(
        ProviderConfig(openai_api_variant="chat_completions", model="qwen3")
    )
    parsed = provider._parse_chat_response(
        {
            "id": "chatcmpl-2",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "1121 非质数，1231 是质数，继续分解 1121。",
                        "tool_calls": [
                            {
                                "id": "call_5b5b",
                                "type": "function",
                                "function": {
                                    "name": "factorize",
                                    "arguments": '{"n": 1121}',
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )
    req = UnifiedLLMRequest(
        provider="openai",
        model="qwen3",
        state=ConversationState(history=parsed.output_items),
        inputs=[],
        instructions="",
        tools=[],
        options=GenerationOptions(),
    )
    compiled = provider._compile_chat_messages(req.state.history, req)

    assert len(compiled) == 1
    assert compiled[0]["role"] == "assistant"
    assert compiled[0]["content"] == ""
    assert compiled[0]["reasoning_content"] == "1121 非质数，1231 是质数，继续分解 1121。"
    assert compiled[0]["tool_calls"][0]["id"] == "call_5b5b"
    assert compiled[0]["tool_calls"][0]["function"]["arguments"] == '{"n": 1121}'


def test_generate_wraps_client_errors_as_provider_error(
    fake_openai: type[FakeOpenAI],
) -> None:
    responses_provider = OpenAIProvider(ProviderConfig(openai_api_variant="responses"))
    responses_client = fake_openai.instances[-1]
    responses_client.responses.error = RuntimeError("boom")
    with pytest.raises(ProviderError, match="OpenAI request failed"):
        responses_provider.generate(_base_req())

    chat_provider = OpenAIProvider(ProviderConfig(openai_api_variant="chat_completions"))
    chat_client = fake_openai.instances[-1]
    chat_client.chat.completions.error = RuntimeError("boom")
    with pytest.raises(ProviderError, match="OpenAI request failed"):
        chat_provider.generate(_base_req())


def test_parse_chat_completion_rejects_missing_choices(
    fake_openai: type[FakeOpenAI],
) -> None:
    provider = OpenAIProvider(ProviderConfig(openai_api_variant="chat_completions"))

    with pytest.raises(ProviderError, match="no choices"):
        provider._parse_chat_response({"id": "x", "choices": []})

    with pytest.raises(ProviderError, match="missing choice message"):
        provider._parse_chat_response({"id": "x", "choices": [{}]})
