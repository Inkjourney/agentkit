# Agent From Config

## Prerequisites

- A valid YAML or JSON config file
- Required provider API key available in environment (unless local vLLM flow)

## Step 1

Write a config file.

```yaml
workspace:
  root: ./workspace

provider:
  kind: openai
  model: gpt-5-mini
  openai_api_variant: responses
  conversation_mode: auto
  api_key_env: OPENAI_API_KEY

agent:
  system_prompt: You are concise and accurate.
  budget:
    max_steps: 10
    time_budget_s: 120
    max_input_chars: 20000

tools:
  entries:
    - ./tools
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

!!! warning
    If you omit `tools.allowed`, the agent will expose no tools. Built-in tools are
    loaded into the registry together with any configured `tools.entries`, but the
    allowlist still controls model visibility.

## Step 2

Build an agent with `create_agent` or `load_config` + `Agent.from_config`.

```python
from agentkit import create_agent

agent = create_agent("agentkit.quickstart.yaml")
```

Equivalent explicit form:

```python
from agentkit.agent import Agent
from agentkit.config import load_config

config = load_config("agentkit.quickstart.yaml")
agent = Agent.from_config(config)
```

## Step 3

Run a task and inspect the returned report.

```python
report = agent.run("Create notes/status.txt with one sentence summary.")
print(report.completed)
print(report.final_output)
print(report.runlog_path)
```

## Full Example

```python
from pathlib import Path

from agentkit import create_agent

config_text = """
workspace:
  root: ./workspace
provider:
  kind: openai
  model: gpt-5-mini
  openai_api_variant: responses
  conversation_mode: auto
  api_key_env: OPENAI_API_KEY
agent:
  system_prompt: You are concise.
  budget:
    max_steps: 10
    time_budget_s: 120
    max_input_chars: 20000
tools:
  allowed: [view, create_file, str_replace, word_count]
runlog:
  enabled: true
  redact: true
  max_text_chars: 20000
""".strip()

path = Path("agentkit.quickstart.yaml")
path.write_text(config_text + "\n", encoding="utf-8")

agent = create_agent(path)
report = agent.run("List files in workspace.")
print(report.final_output)
```

## Expected Output

A successful run returns a `RunReport` and writes a run log file at
`workspace/logs/run_<run_id>.jsonl`.

## Common Pitfalls

- Invalid provider-mode combination (for example `server` mode with chat-completions)
- Missing API key in config or the provider's default environment variable
- Unsupported config fields (loader raises `ConfigError`)
- Forgetting that `tools.allowed` is an allowlist, not a discovery switch

## Related

- [Configuration](../getting-started/configuration.md)
- [Architecture](../concepts/architecture.md)
