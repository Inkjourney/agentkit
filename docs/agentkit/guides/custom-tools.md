# Custom Tools

## Prerequisites

- Familiarity with JSON-schema argument definitions
- Understanding of `ToolRegistry` and `AgentToolRuntime`

## Step 1

Define a custom tool with `FunctionTool`.

```python
from agentkit.tools.base import FunctionTool

slug_tool = FunctionTool(
    name="slugify",
    description="Convert text to a lowercase slug.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    handler=lambda args: {"slug": args["text"].strip().lower().replace(" ", "-")},
)
```

`ToolRegistry` validates only a focused subset of JSON Schema, so keep schemas
simple: `type`, `properties`, `required`, and `additionalProperties`.

## Step 2

Register and execute it through `ToolRegistry`.

```python
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.types import ToolInvocation

registry = ToolRegistry()
registry.register(slug_tool)

outcome = registry.execute(ToolInvocation(name="slugify", arguments={"text": "Agent Kit Docs"}))
print(outcome.is_error, outcome.output)
```

## Step 3

Expose only approved tools to the agent with `AgentToolRuntime`.

```python
from agentkit.agent.tool_runtime import AgentToolRuntime

tool_runtime = AgentToolRuntime(registry, allowed_tools=["slugify"])
print([tool.name for tool in tool_runtime.schemas()])
```

## Step 4

Customize model-facing success or error payloads directly in the tool file when
needed. Success formatters may return either a dictionary or a plain text string.

```python
from agentkit.tools.base import FunctionTool
from agentkit.tools.types import ToolModelError


def run_publish(args: dict[str, str]) -> dict[str, str]:
    if args["channel"] not in {"web", "email"}:
        raise ToolModelError(
            code="unsupported_channel",
            message="The requested publish channel is not supported.",
            hint="Use either 'web' or 'email'.",
            details={"channel": args["channel"]},
        )
    return {"status": "queued"}


publish_tool = FunctionTool(
    name="publish",
    description="Publish content",
    parameters={
        "type": "object",
        "properties": {"channel": {"type": "string"}},
        "required": ["channel"],
        "additionalProperties": False,
    },
    handler=run_publish,
    success_formatter=lambda output, _invocation: (
        f"Publish job queued successfully with status={output['status']}."
    ),
)
```

This keeps custom tool behavior self-contained in one file. You do not need to
edit `ToolRegistry` or `AgentToolRuntime` to define tool-specific model feedback.

## Step 5

If you place your custom tool module under `agentkit.tools.library`, you can let
`load_tools_from_library` discover and register it automatically.

Library modules are discovered when they expose one of these:

- `build_tools(fs)` or `build_tools()`
- `TOOLS`

Modules whose filename starts with `_` are ignored, which is useful for shared helpers.

Example module:

```python
# agentkit/tools/library/slugify.py
from agentkit.tools.base import FunctionTool


TOOLS = [
    FunctionTool(
        name="slugify",
        description="Convert text to a lowercase slug.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=lambda args: {
            "slug": args["text"].strip().lower().replace(" ", "-"),
        },
    )
]
```

Auto-register everything from the library:

```python
from agentkit.tools.loader import load_tools_from_library
from agentkit.tools.registry import ToolRegistry
from agentkit.workspace.fs import WorkspaceFS

workspace_fs = WorkspaceFS("./workspace")
registry = ToolRegistry()
registry.register_many(load_tools_from_library(workspace_fs))
```

## Full Example

```python
from agentkit.agent.tool_runtime import AgentToolRuntime
from agentkit.llm.types import ToolCallItem
from agentkit.tools.base import FunctionTool
from agentkit.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register(
    FunctionTool(
        name="slugify",
        description="Convert text to slug",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=lambda args: {"slug": args["text"].strip().lower().replace(" ", "-")},
    )
)

tool_runtime = AgentToolRuntime(registry, allowed_tools=["slugify"])
call = ToolCallItem(call_id="call-1", name="slugify", arguments={"text": "Agent Kit"})
outcome = tool_runtime.execute(call)
result_item = tool_runtime.build_result_item(outcome)

print(outcome.is_error)
print(result_item.output_text)
```

## Expected Output

```text
False
{"output": {"slug": "agent-kit"}}
```

If your tool uses a string `success_formatter`, `result_item.output_text` will be that string directly instead of JSON.

## Common Pitfalls

- Tool name containing `.` (rejected by `ToolRegistry`)
- Missing required arguments (surfaced as an error outcome)
- Returning unstructured Python exceptions when the tool could raise `ToolModelError` with a clearer message and hint
- Expecting full JSON Schema validation beyond the supported subset
- Forgetting `additionalProperties: False` when strict inputs are required

## Related

- [Tools System Concept](../concepts/tools-system.md)
- [API: tools](../api/tools.md)
