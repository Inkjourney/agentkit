# LLM Providers

## Overview

AgentKit defines a provider-agnostic protocol
`UnifiedLLMRequest -> UnifiedLLMResponse` and ships adapters for five provider
families:

- OpenAI (`responses` and `chat_completions`)
- Anthropic (`messages`)
- Gemini (`generateContent`)
- Qwen (OpenAI-compatible `chat_completions`)
- vLLM (OpenAI-compatible `chat_completions`)

## Why It Exists

Provider APIs differ in request shape, tool-calling format, reasoning metadata, and
finish reasons. AgentKit normalizes those differences into one runtime contract.

## Architecture

```mermaid
graph TD
    A[Agent] --> R[UnifiedLLMRequest]
    R --> F[build_provider(config)]
    F --> O[OpenAIProvider]
    F --> AN[AnthropicProvider]
    F --> G[GeminiProvider]
    F --> Q[QwenProvider]
    F --> V[VLLMProvider]

    O --> U[UnifiedLLMResponse]
    AN --> U
    G --> U
    Q --> U
    V --> U
    U --> A
```

## Key Classes

| Class | Description |
| ----- | ----------- |
| `agentkit.llm.BaseLLMProvider` | Abstract provider interface (`generate`). |
| `agentkit.llm.OpenAIProvider` | OpenAI adapter with two API variants. |
| `agentkit.llm.AnthropicProvider` | Anthropic Messages adapter. |
| `agentkit.llm.GeminiProvider` | Gemini GenerateContent adapter. |
| `agentkit.llm.QwenProvider` | Qwen adapter (OpenAI-compatible). |
| `agentkit.llm.VLLMProvider` | vLLM adapter (OpenAI-compatible). |
| `agentkit.llm.UnifiedLLMResponse` | Normalized status/reason + output items. |

## Provider Matrix

| Provider | Transport | Valid API variant | Conversation modes | Provider-specific behavior |
| --- | --- | --- | --- | --- |
| `openai` | OpenAI SDK | `responses`, `chat_completions` | `auto`, `client`, `server` | `server` mode only works with `responses`. |
| `anthropic` | HTTP `POST /v1/messages` | fixed | `auto`, `client` | Maps `tool_use` blocks to `ToolCallItem`. |
| `gemini` | HTTP `models/{model}:generateContent` | fixed | `auto`, `client` | Tracks `tool_name_by_call_id` in `provider_meta`. |
| `qwen` | OpenAI-compatible chat | `chat_completions` | `auto`, `client` | Sends `enable_thinking` and optional `thinking_budget` in `extra_body`. |
| `vllm` | OpenAI-compatible chat | `chat_completions` | `auto`, `client` | Sends `chat_template_kwargs.enable_thinking` and ignores `reasoning_effort`. |

## How It Works

1. `build_provider` selects implementation from `ProviderConfig.kind`.
2. Agent sends `UnifiedLLMRequest` with state/history, new inputs, tools, and generation options.
3. Provider compiles native request format and calls its backend API.
4. Raw response is parsed into normalized `ConversationItem` objects.
5. Provider maps native finish reasons to unified `status` and `reason`.

Common unified statuses used by runtime:

- `requires_tool`
- `completed`
- `incomplete`
- `blocked`
- `failed`

!!! warning
    `conversation_mode="server"` is only valid for `kind=openai` with `openai_api_variant="responses"`.

## Error Normalization

Provider adapters raise `ProviderError` with an attached `ProviderIssue` whenever
they can classify the failure. Categories currently include:

- `auth`
- `rate_limit`
- `invalid_request`
- `timeout`
- `upstream`
- `safety`
- `parse`
- `unknown`

## Reasoning And Tool Replay

Providers may emit `ReasoningItem` values in addition to assistant text and tool
calls. The core adapters preserve replay information when it is safe to send back
to the same provider on the next turn.

!!! note
    Behavior inferred from code inspection: reasoning artifacts are provider-aware.
    OpenAI reasoning items are replayed back to OpenAI, but not blindly copied into
    Gemini requests.

## Example

```python
from agentkit.config.schema import ProviderConfig
from agentkit.llm.factory import build_provider

provider = build_provider(
    ProviderConfig(
        kind="openai",
        model="gpt-5-mini",
        openai_api_variant="responses",
        api_key="test-key",
    )
)

print(type(provider).__name__)
```

## Related Concepts

- [Agent Lifecycle](./agent-lifecycle.md)
- [Tools System](./tools-system.md)
- [API: llm](../api/llm.md)
