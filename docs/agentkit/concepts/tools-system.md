# Tools System

## Overview

Tools are model-callable functions exposed through `ToolRegistry` and executed by
`AgentToolRuntime` during agent runs.

## Why It Exists

The tool system separates model reasoning from side-effecting operations, with
schema validation, stable error payloads, and allowlist filtering.

## Architecture

```mermaid
flowchart TD
    A[Tool module] --> B[build_tools(fs) or TOOLS]
    B --> C[load_tools_from_library]
    C --> D[ToolRegistry.register_many]
    D --> E[AgentToolRuntime]
    E --> F[tool schemas in model request]
    G[ToolCallItem from model] --> E
    E --> H[ToolRegistry.execute]
    H --> I[ToolCallOutcome]
    I --> J[ToolResultItem]
    J --> K[next model turn inputs]
```

## Key Classes

| Class | Description |
| ----- | ----------- |
| `agentkit.tools.Tool` | Base interface for tools. |
| `agentkit.tools.FunctionTool` | Callable-backed tool implementation. |
| `agentkit.tools.ToolRegistry` | Registers, validates, and executes tools. |
| `agentkit.tools.ToolModelError` | Tool-defined structured error for model-facing feedback. |
| `agentkit.tools.load_tools_from_library` | Auto-discovers tool modules in `agentkit.tools.library`. |
| `agentkit.agent.AgentToolRuntime` | Applies allowlist and bridges tool calls/results for agent loop. |

Built-in tools from `agentkit.tools.library.fs_tools`:

- `view`
- `create_file`
- `str_replace`
- `word_count`

## Built-In Tool Behavior

| Tool | Primary use | Notes |
| --- | --- | --- |
| `view` | Read files or inspect directories | Directory output skips dotfiles, `node_modules`, and `__pycache__`; file payloads are line-numbered and truncated for model context safety. |
| `create_file` | Create or overwrite files | Always overwrites existing files; prefer `str_replace` for localized edits. |
| `str_replace` | Replace one exact string occurrence | Requires a unique exact match for `old_str`. |
| `word_count` | Report file metrics | `word_count` is a platform-specific character-count heuristic, not natural-language tokenization. |

## How It Works

1. Agent initialization loads library modules and registers their tools.
2. Tool schemas are passed to the provider in each model call.
3. Model outputs `ToolCallItem` values when tool use is needed.
4. `AgentToolRuntime.execute` validates allowlist and delegates to `ToolRegistry.execute`.
5. Tools can customize model-facing success/error payloads in the tool file via formatter hooks or `ToolModelError`.
6. The canonical tool outcome is wrapped as `ToolResultItem` and fed into the next model turn.

## Validation Model

`ToolRegistry` validates a focused subset of JSON Schema:

- `type`
- `properties`
- `required`
- `additionalProperties`

!!! note
    Behavior inferred from code inspection: full JSON Schema features such as
    nested combinators, numeric bounds, or string patterns are not enforced by
    `ToolRegistry`.

## Model-Facing Payloads

`ToolCallOutcome.output` and the payload sent back to the model do not have to be the same.

- `output` is the full tool result kept for runtime inspection, tests, and logs.
- `model_payload` is the compact payload that will be replayed into the next model turn.

When run logging is enabled, `tool_executed` events record both fields so you can compare the raw tool result with the smaller or more natural-language payload that the model actually consumed.

`model_payload` can be either:

- a structured dictionary, when the model benefits from stable machine-readable fields
- a plain text string, when the tool should read more like an observation than a data object

This is useful when a tool needs rich diagnostics internally but should give the model only the fields it actually needs. The built-in filesystem tools use this heavily:

- `word_count` keeps detailed metrics in `output`, but sends the model a short sentence such as `The file chapter-03.md has 3201 words across 47 lines.`
- `create_file` keeps write metadata in `output`, but sends the model a sentence such as `File created: chapters/03.md (120 lines, 3.1KB, 980 words)`.
- `view` keeps structured file or directory metadata in `output`, but sends the model a formatted text block with headers, right-aligned numbered lines, or a tree-style directory listing.

When `AgentToolRuntime.build_result_item` creates a `ToolResultItem`, the payload remains whatever the tool formatter returned. Provider adapters send string payloads as-is, and serialize dictionary payloads as JSON text.

## Allowlist Semantics

`Agent.from_config` registers the built-in library first, then constructs
`AgentToolRuntime(registry, config.tools.allowed)`.

!!! warning
    An empty `tools.allowed` list disables all model-visible tools. This is the
    default behavior of `ToolConfig()`.

## Example

```python
from agentkit.tools.base import FunctionTool
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.types import ToolInvocation

registry = ToolRegistry()
registry.register(
    FunctionTool(
        name="echo",
        description="Echo text",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=lambda args: {"echo": args["text"]},
    )
)

outcome = registry.execute(ToolInvocation(name="echo", arguments={"text": "hello"}))
print(outcome.is_error, outcome.output)
```

## Related Concepts

- [Agent Lifecycle](./agent-lifecycle.md)
- [Workspace](./workspace.md)
- [Guide: Custom Tools](../guides/custom-tools.md)
