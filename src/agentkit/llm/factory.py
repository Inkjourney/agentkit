"""Provider factory for constructing configured LLM backends."""

from __future__ import annotations

from agentkit.config.schema import ProviderConfig
from agentkit.errors import ConfigError
from agentkit.llm.base import BaseLLMProvider
from agentkit.llm.providers.anthropic_provider import AnthropicProvider
from agentkit.llm.providers.gemini_provider import GeminiProvider
from agentkit.llm.providers.openai_provider import OpenAIProvider
from agentkit.llm.providers.qwen_provider import QwenProvider
from agentkit.llm.providers.vllm_provider import VLLMProvider


def build_provider(config: ProviderConfig) -> BaseLLMProvider:
    """Create the configured provider implementation."""
    if config.kind == "openai":
        return OpenAIProvider(config)
    if config.kind == "anthropic":
        return AnthropicProvider(config)
    if config.kind == "gemini":
        return GeminiProvider(config)
    if config.kind == "vllm":
        return VLLMProvider(config)
    if config.kind == "qwen":
        return QwenProvider(config)
    raise ConfigError(f"Unsupported provider kind: {config.kind}")
