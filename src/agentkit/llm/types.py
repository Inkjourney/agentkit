"""Unified provider-agnostic LLM request/response and conversation types."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

ProviderKind = Literal["openai", "anthropic", "gemini", "vllm", "qwen"]
ConversationMode = Literal["auto", "client", "server"]

TurnStatus = Literal["completed", "requires_tool", "incomplete", "blocked", "failed"]
CompletionReason = Literal[
    "stop",
    "tool_call",
    "max_tokens",
    "content_filter",
    "refusal",
    "pause",
    "context_window",
    "error",
    "unknown",
]


@dataclass(slots=True)
class MessageItem:
    """Plain-text message stored in unified conversation history.

    Attributes:
        role: Logical speaker for the message.
        text: Provider-normalized text payload.
    """

    role: Literal["user", "assistant"]
    text: str


@dataclass(slots=True)
class ToolCallItem:
    """Structured tool request emitted by a provider.

    Attributes:
        call_id: Stable identifier used to match the eventual tool result.
        name: Registered tool name to execute.
        arguments: Parsed arguments when the provider returned valid JSON.
        raw_arguments: Original serialized arguments, preserved for replay fidelity.
    """

    call_id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str | None = None


@dataclass(slots=True)
class ToolResultItem:
    """Tool execution result appended back into conversation history.

    Attributes:
        call_id: Identifier of the tool call this result satisfies.
        tool_name: Tool name, retained for providers that require it on replay.
        payload: Model-facing success or error payload.
        is_error: Whether the tool execution failed.
    """

    call_id: str
    tool_name: str | None = None
    payload: Any = field(default_factory=dict)
    is_error: bool = False

    @property
    def output_text(self) -> str:
        """Return the payload as text for providers that require string content."""
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False)


@dataclass(slots=True)
class ReasoningItem:
    """Provider reasoning artifact captured separately from assistant text.

    Attributes:
        text: Full reasoning text when the provider exposes it.
        summary: Shorter reasoning summary when full text is unavailable.
        raw_item: Original provider payload used for transcript replay.
        replay_hint: Whether the raw payload should be sent back on future turns.
    """

    text: str | None
    summary: str | None = None
    raw_item: dict[str, Any] | None = None
    replay_hint: bool = True


ConversationItem = MessageItem | ToolCallItem | ToolResultItem | ReasoningItem


@dataclass(slots=True)
class ConversationState:
    """Mutable provider conversation state carried across turns.

    Attributes:
        mode: Whether conversation state is managed by the client or provider.
        history: Canonical transcript items that have already been committed.
        provider_cursor: Provider-issued cursor or response id for server-side state.
        provider_meta: Provider-specific metadata needed to continue a session.
    """

    mode: ConversationMode = "auto"
    history: list[ConversationItem] = field(default_factory=list)
    provider_cursor: str | None = None
    provider_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UnifiedToolSpec:
    """Model-facing description of one callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(slots=True)
class GenerationOptions:
    """Per-request generation knobs after config defaults are applied."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    stop_sequences: list[str] | None = None
    thinking_enabled: bool | None = None
    reasoning_effort: str | None = None


@dataclass(slots=True)
class UnifiedLLMRequest:
    """Provider-agnostic request assembled for one model turn.

    Attributes:
        provider: Selected provider backend.
        model: Provider model identifier.
        state: Conversation state from previous turns.
        inputs: New conversation items to append for this turn.
        instructions: System-level instructions for the turn.
        tools: Tool schemas exposed to the provider.
        options: Request-level generation overrides.
    """

    provider: ProviderKind
    model: str
    state: ConversationState
    inputs: list[ConversationItem]
    instructions: str
    tools: list[UnifiedToolSpec]
    options: GenerationOptions


@dataclass(slots=True)
class Usage:
    """Normalized token accounting returned by providers."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class StatePatch:
    """Incremental provider-state update returned after a model turn."""

    new_provider_cursor: str | None = None
    provider_meta_patch: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UnifiedLLMResponse:
    """Provider-agnostic response produced for one model turn.

    Attributes:
        response_id: Provider response identifier when available.
        status: High-level turn status used by the agent loop.
        reason: Normalized completion reason.
        output_items: Canonical output items emitted by the provider.
        output_text: Human-facing assistant text synthesized from ``output_items``.
        usage: Normalized token usage information.
        state_patch: Provider-state updates to apply after committing the turn.
        provider_name: Provider that produced the response.
        raw_response: Original provider payload for debugging and replay support.
    """

    response_id: str | None
    status: TurnStatus
    reason: CompletionReason
    output_items: list[ConversationItem]
    output_text: str
    usage: Usage
    state_patch: StatePatch
    provider_name: ProviderKind
    raw_response: dict[str, Any] | None = None

    @property
    def tool_calls(self) -> list[ToolCallItem]:
        """Return only tool calls from ``output_items`` for the agent loop."""
        return [item for item in self.output_items if isinstance(item, ToolCallItem)]

    @property
    def has_tool_calls(self) -> bool:
        """Report whether the provider requested at least one tool execution."""
        return any(isinstance(item, ToolCallItem) for item in self.output_items)
