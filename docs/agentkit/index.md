# AgentKit

AgentKit is a Python framework for running tool-using LLM agents with a single
runtime model:

- one unified request/response contract across providers
- workspace-isolated file operations
- registry-driven tools
- structured run logs to JSONL
- Python SDK and CLI interfaces

## What You Build With It

Use AgentKit when you need agents that can:

- reason over multi-turn state
- call tools and continue with tool outputs
- run under step/time budgets
- record trace logs for debugging

## Main Building Blocks

| Component | Purpose |
| --- | --- |
| `agent` | Agent loop, run reports, budgets, tool orchestration |
| `llm` | Provider-agnostic types and provider adapters |
| `tools` | Tool abstractions, registry, and module loader |
| `workspace` | Strict filesystem isolation |
| `runlog` | Event model, sink interfaces, and JSONL run logs |
| `config` | Dataclass config schema + YAML/JSON loader |
| `cli` | `llm-agent` parser and command dispatch |
| `errors` | Framework exceptions and provider issue metadata |

## Next Steps

- [Install AgentKit](./getting-started/installation.md)
- [Run Your First Agent](./getting-started/quickstart.md)
- [Learn the Configuration Model](./getting-started/configuration.md)
- [Understand Runtime Architecture](./concepts/architecture.md)
