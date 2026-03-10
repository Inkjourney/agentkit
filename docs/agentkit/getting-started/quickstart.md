# Quickstart

This guide runs one task through the full AgentKit loop:

`task -> provider turn -> tool call -> tool result -> final report`

## 1. Create a Config File

Create `agentkit.quickstart.yaml`:

```yaml
workspace:
  root: ./workspace

provider:
  kind: openai
  model: gpt-5-mini
  openai_api_variant: responses
  conversation_mode: auto
  api_key_env: OPENAI_API_KEY
  temperature: 0.2

agent:
  system_prompt: You are a concise assistant. Use tools when needed.
  budget:
    max_steps: 10
    time_budget_s: 120
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

!!! note
    `tools.allowed` matters. AgentKit loads the built-in library during
    `Agent.from_config`, but the agent can only call tools that appear in this
    allowlist. The default `ToolConfig()` value is an empty list, which exposes
    no tools.

## 2. Set Your API Key

```bash
export OPENAI_API_KEY="your-key"
```

## 3. Run From Python

```python
from pathlib import Path

from agentkit import create_agent

config_path = Path("agentkit.quickstart.yaml")
agent = create_agent(config_path)

report = agent.run(
    "Create notes/todo.txt with three short bullet items for today, "
    "then tell me where you saved it."
)

print("completed:", report.completed)
print("status:", report.status)
print("output:", report.final_output)
print("run log:", report.runlog_path)
```

## 4. Run From CLI

```bash
uv run agentkit --config agentkit.quickstart.yaml run \
  --task "List files in this workspace" \
  --report-json ./report.json
```

## Expected Output

You should see:

- the assistant final text in stdout
- a `RunReport` JSON file when `--report-json` is provided
- a run log file under `workspace/logs/run_<run_id>.jsonl`

## Common Pitfalls

- Missing API key in config or the provider's default environment variable
- Restrictive `tools.allowed` list that blocks required tool calls
- Too-low `max_steps` for multi-step tasks
- Using the default config without a `tools.allowed` list and expecting built-in tools to work

## Related

- [Configuration](./configuration.md)
- [Agent Lifecycle](../concepts/agent-lifecycle.md)
- [CLI Usage Guide](../guides/cli-usage.md)
