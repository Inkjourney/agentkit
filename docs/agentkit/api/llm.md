# LLM API

## Overview

The `llm` package provides:

- provider-agnostic request/response types
- provider interfaces
- provider factory helpers
- token-usage utilities
- built-in provider adapters

## Key Classes

- `BaseLLMProvider`
- `UnifiedLLMRequest` / `UnifiedLLMResponse`
- `ConversationState`, `ToolCallItem`, `ToolResultItem`, `ReasoningItem`
- `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`, `QwenProvider`, `VLLMProvider`

## API Reference

::: agentkit.llm

::: agentkit.llm.base

::: agentkit.llm.types

::: agentkit.llm.factory

::: agentkit.llm.usage

::: agentkit.llm.providers.openai_provider

::: agentkit.llm.providers.anthropic_provider

::: agentkit.llm.providers.gemini_provider

::: agentkit.llm.providers.qwen_provider

::: agentkit.llm.providers.vllm_provider

## Notes

Provider adapters normalize native response states into unified `status` and
`reason` fields.

`ConversationState.provider_cursor` and `ConversationState.provider_meta` are the
extension points used by built-in providers to preserve provider-specific
continuation state.
