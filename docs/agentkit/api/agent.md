# Agent API

## Overview

The agent runtime surface centers on two entry points:

- `agentkit.create_agent(...)` for config-based construction
- `agentkit.agent.Agent` for direct runtime construction

Supporting modules provide budget guards, tool-runtime bridging, and run-report
projection from canonical run events.

## Key Classes

- `Agent`: main runtime loop and config-based constructor.
- `RuntimeBudget`: step/time guard checked before each iteration.
- `RunReport`: serialized run output container, including projected tool calls.
- `RunStep` and `RunToolCall`: nested report record types.
- `AgentToolRuntime`: allowlist + tool call/result bridge.
- `RunReportProjector`: event sink that materializes `RunReport`.

## API Reference

::: agentkit

::: agentkit.agent

::: agentkit.agent.agent

::: agentkit.agent.budgets

::: agentkit.agent.report

::: agentkit.agent.tool_runtime

## Notes

`Agent.run` is the core lifecycle method and returns `RunReport`.

`RunReport.tool_calls[*]` preserves:

- `output`: the raw tool result
- `error`: the execution error string when the tool failed
- `model_payload`: the exact payload that was replayed into the next model turn
