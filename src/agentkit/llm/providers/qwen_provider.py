"""Qwen provider via OpenAI-compatible Chat Completions API."""

from __future__ import annotations

from typing import Any

from agentkit.config.schema import ProviderConfig
from agentkit.llm.providers.openai_provider import OpenAIProvider
from agentkit.llm.types import UnifiedLLMRequest, UnifiedLLMResponse


class QwenProvider(OpenAIProvider):
    """Qwen adapter using OpenAI-compatible chat.completions."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        response = super().generate(req)
        response.provider_name = "qwen"
        return response

    def _extra_chat_kwargs(self, req: UnifiedLLMRequest) -> dict[str, Any]:
        thinking_enabled = req.options.thinking_enabled
        if thinking_enabled is None:
            thinking_enabled = self.config.enable_thinking

        extra_body: dict[str, Any] = {
            "enable_thinking": bool(thinking_enabled),
        }
        if self.config.thinking_budget is not None:
            extra_body["thinking_budget"] = self.config.thinking_budget

        return {"extra_body": extra_body}
