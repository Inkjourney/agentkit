# Configuration

AgentKit loads YAML or JSON into `AgentkitConfig` with
`agentkit.config.load_config`.

## Overview

Configuration has two jobs:

- define runtime behavior through dataclass models in `agentkit.config.schema`
- normalize provider defaults such as API key environment variables and base URLs

The loader signature is:

```python
from agentkit.config import load_config

config = load_config(
    "agentkit.yaml",
    overrides={"agent": {"system_prompt": "Be precise."}},
)
```

## Supported File Types

- `.yaml` / `.yml`
- `.json`

Other suffixes raise `ConfigError`.

## Top-Level Schema

| Key | Model | Default |
| --- | --- | --- |
| `workspace` | `WorkspaceConfig` | `{"root": "./workspace"}` |
| `provider` | `ProviderConfig` | OpenAI defaults |
| `agent` | `AgentConfig` | system prompt + default budget |
| `tools` | `ToolConfig` | empty allowlist/entries |
| `runlog` | `RunLogConfig` | enabled/redacted, `max_text_chars=20000` |

## `workspace`

| Field | Type | Default |
| --- | --- | --- |
| `root` | `str` | `"./workspace"` |

## `provider`

| Field | Type | Default |
| --- | --- | --- |
| `kind` | `Literal["openai","anthropic","gemini","vllm","qwen"]` | `"openai"` |
| `model` | `str` | `"gpt-5"` |
| `openai_api_variant` | `Literal["responses","chat_completions"]` | `"responses"` |
| `conversation_mode` | `Literal["auto","client","server"]` | `"auto"` |
| `temperature` | `float | None` | `0.2` |
| `timeout_s` | `int` | `60` |
| `retries` | `int` | `2` |
| `api_key` | `str | None` | `None` |
| `api_key_env` | `str | None` | `None` |
| `base_url` | `str | None` | `None` |
| `reasoning_effort` | `str | None` | `None` |
| `enable_thinking` | `bool` | `True` |
| `thinking_budget` | `int | None` | `None` |

Validation rules include:

- `timeout_s > 0`, `retries >= 0`
- `thinking_budget > 0` when provided
- `conversation_mode="server"` only for `kind=openai` + `openai_api_variant=responses`
- `kind in {"vllm","qwen"}` requires `openai_api_variant=chat_completions`
- `kind in {"anthropic","gemini"}` does not allow custom `openai_api_variant`

### Provider Defaults

When fields are omitted, AgentKit fills in provider defaults through
`agentkit.config.provider_defaults`:

| Provider | Default `api_key_env` | Default `base_url` |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY` | provider SDK default |
| `anthropic` | `ANTHROPIC_API_KEY` | `https://api.anthropic.com` |
| `gemini` | `GEMINI_API_KEY` | `https://generativelanguage.googleapis.com/v1beta` |
| `qwen` | `DASHSCOPE_API_KEY` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `vllm` | `VLLM_API_KEY` | `http://localhost:8000/v1` |

### Conversation Modes

| Mode | Meaning |
| --- | --- |
| `client` | Send full conversation history every turn. |
| `server` | Use provider-managed conversation state. Only supported for OpenAI Responses. |
| `auto` | Start like `client`; switch to cursor-based continuation once a provider cursor exists. |

!!! warning
    `conversation_mode="server"` is only supported for
    `kind="openai"` with `openai_api_variant="responses"`.

## `agent`

| Field | Type | Default |
| --- | --- | --- |
| `system_prompt` | `str` | `"You are a helpful agent. Use tools when needed."` |
| `budget` | `BudgetConfig` | see below |

### `agent.budget`

| Field | Type | Default |
| --- | --- | --- |
| `max_steps` | `int` | `20` |
| `time_budget_s` | `int` | `300` |
| `max_input_chars` | `int` | `20000` |

All budget values must be positive.

!!! note
    Behavior inferred from code inspection: `Agent.run` currently enforces
    `max_steps` and `time_budget_s`, but does not enforce `max_input_chars`.
    The field is validated and stored in config, not consumed by the runtime.

## `tools`

| Field | Type | Default |
| --- | --- | --- |
| `allowed` | `list[str]` | `[]` |
| `entries` | `list[str]` | `[]` |

`allowed` controls which discovered tools the agent can call.

`entries` lists custom tool files or directories to load in addition to the
built-in tool library.

!!! warning
    The default `allowed=[]` means the agent exposes no tools, even though
    `Agent.from_config` still loads the built-in tool library and any configured
    `tools.entries` into the registry.

Relative `tools.entries` paths are resolved against the config file location.

Directory entries are discovered in sorted order. `__init__.py` is loaded first
when present, and child files whose name starts with `_` are ignored during
directory auto-discovery.

## `runlog`

| Field | Type | Default |
| --- | --- | --- |
| `enabled` | `bool` | `True` |
| `redact` | `bool` | `True` |
| `max_text_chars` | `int` | `20000` |

`max_text_chars` must be positive.

## Environment Expansion

Config values matching `${ENV_NAME}` are expanded recursively by the loader.
The placeholder must occupy the entire string value.

Example:

```yaml
provider:
  kind: openai
  api_key: ${OPENAI_API_KEY}
```

## API Key Injection

When `api_key` is missing, the loader checks `api_key_env` and then provider
defaults. Missing credentials raise `ConfigError` except for local vLLM
endpoints (`localhost` or `127.0.0.1`), which may omit an API key.

!!! note
    Behavior inferred from code inspection: local vLLM runs still inject a dummy
    client key at OpenAI SDK construction time so the compatible client can be
    instantiated without a real secret.

## Complete Example

```yaml
workspace:
  root: ./workspace

provider:
  kind: qwen
  model: qwen3-max-2026-01-23
  openai_api_variant: chat_completions
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  api_key_env: DASHSCOPE_API_KEY
  enable_thinking: true
  thinking_budget: 4096

agent:
  system_prompt: You are a careful coding assistant.
  budget:
    max_steps: 12
    time_budget_s: 180
    max_input_chars: 20000

tools:
  allowed:
    - view
    - create_file
    - str_replace
    - word_count

runlog:
  enabled: true
  redact: true
  max_text_chars: 20000
```

## Related

- [Agent From Config Guide](../guides/agent-from-config.md)
- [LLM Providers](../concepts/llm-providers.md)
