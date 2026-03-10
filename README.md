# AgentKit

[中文版本](docs/README.zh-CN.md)

AgentKit is a general-purpose framework for tool-using LLM agents. It provides
workspace isolation, a unified LLM abstraction, a tool-execution loop, and both
CLI and Python SDK entry points.

## Current Capabilities

- Strong workspace isolation: all agent-visible file access goes through
  `WorkspaceFS`
- Unified LLM abstraction:
  `ConversationItem` / `ConversationState` / `UnifiedLLMRequest` /
  `UnifiedLLMResponse`
- Provider support (sync, non-streaming, text)
  - OpenAI (`responses` / `chat_completions`)
  - Anthropic (`messages`)
  - Gemini (`generateContent`)
  - Qwen (OpenAI-compatible `chat_completions`)
  - vLLM (OpenAI-compatible `chat_completions`)
- Registry-based tool system with built-in tools under
  `src/agentkit/tools/library/`
- Agent loop that coordinates model reasoning and tool execution under step/time
  budgets
- Run logs written to `workspace/logs/run_<run_id>.jsonl`

## Status

- The repository includes unit tests for the agent loop, CLI, tool system,
  runlog, and the OpenAI / Anthropic / Gemini / Qwen / vLLM provider adapters
- There is no smoke-test coverage against live upstream APIs yet, so a final
  end-to-end validation against the target model is still recommended before
  production use

## Documentation

Full documentation lives under `docs/agentkit/`.

## Install From Source

```bash
uv sync
uv run agentkit --help
```

## Install From PyPI

```bash
pip install base-agentkit
agentkit --help
```

The import path and CLI command stay the same after installation:

```python
from agentkit import create_agent
```

## Example Configuration

### vLLM

```yaml
workspace:
  root: "./vllm_workspace"

provider:
  kind: "vllm"
  model: "glm-5"
  openai_api_variant: "chat_completions"
  conversation_mode: "auto"
  base_url: "http://localhost:8000/v1"
  api_key: "empty"
  temperature: 0.8
  timeout_s: 600
  retries: 2
  enable_thinking: true

agent:
  system_prompt: "You are a helpful agent. Use tools when needed."
  budget:
    max_steps: 200
    time_budget_s: 1800
    max_input_chars: 180000

tools:
  allowed:
    - "view"
    - "create_file"
    - "str_replace"
    - "word_count"

runlog:
  enabled: true
  redact: true
  max_text_chars: 20000
```

## Run From The CLI

```bash
export OPENAI_API_KEY="your-key"
uv run agentkit --config path/to/config.yaml run --task "List the files in the current workspace"
```

## Python SDK

```python
from agentkit import create_agent

agent = create_agent("path/to/config.yaml")
report = agent.run("Create notes/todo.txt in the workspace and write today's plan")
print(report.final_output)
```

## Project Layout

The core implementation lives under `src/agentkit/`:

- `config/`: configuration schema and loader
- `workspace/`: strict filesystem isolation and workspace layout
- `llm/`: unified abstractions, provider base/factory, and adapters
- `tools/`: tool abstractions, registry, and autoloading
- `agent/`: budgets, reports, runtime, and the agent loop
- `runlog/`: structured events, event sinks, and JSONL runlogs
- `cli/`: command-line entry point
