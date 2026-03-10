# AgentKit Documentation

AgentKit is a Python framework for building tool-using LLM agents around a small set
of explicit runtime primitives:

- `Agent` coordinates model calls, tool execution, and run logging
- `WorkspaceFS` keeps file access inside a workspace root
- `UnifiedLLMRequest` and `UnifiedLLMResponse` normalize provider behavior
- `ToolRegistry` and `AgentToolRuntime` expose validated tools to the model
- `RunRecorder` and `JsonlRunLogSink` emit canonical JSONL run logs

This documentation is maintained against the current source in `src/agentkit/`.

!!! note
    Examples and filesystem paths in this site are written for the repository
    root layout used by this project.

## Start Here

- [AgentKit Overview](./agentkit/index.md)
- [Installation](./agentkit/getting-started/installation.md)
- [Quickstart](./agentkit/getting-started/quickstart.md)
- [Configuration](./agentkit/getting-started/configuration.md)

## Core Concepts

- [Architecture](./agentkit/concepts/architecture.md)
- [Agent Lifecycle](./agentkit/concepts/agent-lifecycle.md)
- [LLM Providers](./agentkit/concepts/llm-providers.md)
- [Tools System](./agentkit/concepts/tools-system.md)
- [Budgets](./agentkit/concepts/budgets.md)
- [Run Log](./agentkit/concepts/tracing.md)
- [Workspace](./agentkit/concepts/workspace.md)

## Guides

- [Build a Manual Provider Adapter](./agentkit/guides/custom-llm-provider.md)
- [Build Custom Tools](./agentkit/guides/custom-tools.md)
- [Create an Agent from Config](./agentkit/guides/agent-from-config.md)
- [Use the CLI](./agentkit/guides/cli-usage.md)

## API Reference

- [Agent API](./agentkit/api/agent.md)
- [LLM API](./agentkit/api/llm.md)
- [Tools API](./agentkit/api/tools.md)
- [Config API](./agentkit/api/config.md)
- [Run Log API](./agentkit/api/tracing.md)
- [Workspace API](./agentkit/api/workspace.md)
- [Errors API](./agentkit/api/errors.md)
- [CLI API](./agentkit/api/cli.md)
