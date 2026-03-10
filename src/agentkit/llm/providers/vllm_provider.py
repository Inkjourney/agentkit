"""vLLM OpenAI-compatible provider."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agentkit.config.provider_defaults import is_localhost_base_url
from agentkit.config.schema import ProviderConfig
from agentkit.llm.providers.openai_provider import OpenAIProvider
from agentkit.llm.types import UnifiedLLMRequest, UnifiedLLMResponse

_LOCAL_VLLM_CLIENT_API_KEY = "empty"


class VLLMProvider(OpenAIProvider):
    """OpenAI chat-compatible adapter with vLLM-specific request flags."""

    def __init__(self, config: ProviderConfig) -> None:
        client_config = replace(config)
        if client_config.api_key is None and is_localhost_base_url(
            client_config.base_url
        ):
            client_config.api_key = _LOCAL_VLLM_CLIENT_API_KEY
        super().__init__(client_config)
        self.config = config

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        response = super().generate(req)
        response.provider_name = "vllm"
        return response

    def _allow_reasoning_effort(self) -> bool:
        # vLLM's OpenAI-compatible server does not support reasoning_effort.
        return False

    def _extra_chat_kwargs(self, req: UnifiedLLMRequest) -> dict[str, Any]:
        thinking_enabled = req.options.thinking_enabled
        if thinking_enabled is None:
            thinking_enabled = self.config.enable_thinking
        return {
            "extra_body": {
                "chat_template_kwargs": {
                    "enable_thinking": bool(thinking_enabled),
                }
            }
        }
