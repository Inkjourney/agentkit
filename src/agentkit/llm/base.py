"""Base abstractions for unified LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentkit.llm.types import (
    ConversationItem,
    MessageItem,
    UnifiedLLMRequest,
    UnifiedLLMResponse,
)


class BaseLLMProvider(ABC):
    """Abstract interface implemented by provider adapters."""

    model: str

    @abstractmethod
    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        """Execute one non-streaming model turn and return unified output."""

    def render_output_text(
        self,
        output_items: list[ConversationItem],
        raw_response: dict[str, object] | None,
    ) -> str:
        """Render provider-specific human-facing text from output items."""
        del raw_response
        texts = [
            item.text
            for item in output_items
            if isinstance(item, MessageItem) and item.role == "assistant"
        ]
        return "\n".join(texts).strip()
