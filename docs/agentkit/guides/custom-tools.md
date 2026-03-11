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

Load custom tools through `tools.entries`.

After installing AgentKit, keep your custom tool modules in your own project and
point config at either:

- a Python file such as `./tools/slugify.py`
- a directory such as `./tools`

Each loaded module may expose tools via:

- `build_tools(fs)` or `build_tools()`
- `TOOLS`

Directory entries behave like a lightweight tool library:

- `__init__.py` is loaded first when present
- direct child `.py` files are discovered in sorted order
- child files whose name starts with `_` are ignored for discovery, which is useful for shared helpers

Example project layout:

```text
my-project/
├─ agentkit.yaml
└─ tools/
   ├─ slugify.py
   └─ _shared.py
```

Example module:

```python
# tools/slugify.py
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

Example config:

```yaml
tools:
  entries:
    - ./tools
  allowed:
    - slugify
```

Relative `tools.entries` paths are resolved against the config file location.

If you are wiring tools manually in Python, you can load the same entries with
`load_tools_from_entries(...)`:

```python
from agentkit.tools.loader import load_tools_from_entries
from agentkit.tools.registry import ToolRegistry
from agentkit.workspace.fs import WorkspaceFS

workspace_fs = WorkspaceFS("./workspace")
registry = ToolRegistry()
registry.register_many(load_tools_from_entries(["./tools"], workspace_fs))
```

AgentKit's own built-in tools still live under `agentkit.tools.library`, but
user-defined tools no longer need to be added there.

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
