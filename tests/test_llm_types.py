from __future__ import annotations

from agentkit.llm.types import (
    ConversationState,
    GenerationOptions,
    MessageItem,
    StatePatch,
    ToolCallItem,
    ToolResultItem,
    UnifiedLLMRequest,
    UnifiedLLMResponse,
    UnifiedToolSpec,
    Usage,
)


def test_unified_llm_response_tool_call_properties() -> None:
    response_without_calls = UnifiedLLMResponse(
        response_id=None,
        status="completed",
        reason="stop",
        output_items=[MessageItem(role="assistant", text="hello")],
        output_text="hello",
        usage=Usage(),
        state_patch=StatePatch(),
        provider_name="openai",
    )
    response_with_calls = UnifiedLLMResponse(
        response_id="r1",
        status="requires_tool",
        reason="tool_call",
        output_items=[
            ToolCallItem(call_id="c1", name="echo", arguments={"text": "x"}),
            MessageItem(role="assistant", text="calling tool"),
        ],
        output_text="calling tool",
        usage=Usage(),
        state_patch=StatePatch(),
        provider_name="openai",
    )

    assert response_without_calls.has_tool_calls is False
    assert response_without_calls.tool_calls == []

    assert response_with_calls.has_tool_calls is True
    assert [call.name for call in response_with_calls.tool_calls] == ["echo"]


def test_unified_llm_request_and_state_dataclasses() -> None:
    state = ConversationState(mode="auto")
    req = UnifiedLLMRequest(
        provider="openai",
        model="gpt-5",
        state=state,
        inputs=[
            MessageItem(role="user", text="hello"),
            ToolResultItem(call_id="c1", tool_name="echo", payload={}),
        ],
        instructions="be precise",
        tools=[
            UnifiedToolSpec(
                name="echo",
                description="Echo",
                parameters={"type": "object", "properties": {}, "required": []},
            )
        ],
        options=GenerationOptions(temperature=0.1, reasoning_effort="medium"),
    )

    assert req.provider == "openai"
    assert req.state.history == []
    assert req.instructions == "be precise"
    assert req.tools[0].name == "echo"
    assert req.options.reasoning_effort == "medium"
