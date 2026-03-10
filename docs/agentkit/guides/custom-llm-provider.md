# Custom LLM Provider

## Prerequisites

- You understand `UnifiedLLMRequest` and `UnifiedLLMResponse`
- You can construct `Agent` runtime components directly
- Python 3.12+ environment with AgentKit installed

## What This Guide Covers

This guide shows how to wire a manual provider adapter into `Agent`. It does not
add a new `ProviderConfig.kind` to `build_provider`.

!!! note
    Behavior inferred from code inspection: config-based provider selection is
    closed over the built-in kinds `openai`, `anthropic`, `gemini`, `vllm`, and
    `qwen`. A custom adapter is therefore a manual runtime-construction pattern,
    not a drop-in config extension point.

## Step 1

Implement a class that extends `BaseLLMProvider` and returns a valid `UnifiedLLMResponse`.

```python
from agentkit.llm.base import BaseLLMProvider
from agentkit.llm.types import (
    MessageItem,
    StatePatch,
    UnifiedLLMRequest,
    UnifiedLLMResponse,
    Usage,
)


class EchoProvider(BaseLLMProvider):
    model = "echo-model"

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        prompt = ""
        for item in req.inputs:
            if isinstance(item, MessageItem) and item.role == "user":
                prompt = item.text

        return UnifiedLLMResponse(
            response_id="echo-1",
            status="completed",
            reason="stop",
            output_items=[MessageItem(role="assistant", text=f"echo: {prompt}")],
            output_text=f"echo: {prompt}",
            usage=Usage(),
            state_patch=StatePatch(),
            provider_name="openai",
            raw_response={"provider": "echo"},
        )
```

`status`, `reason`, and `output_items` must stay internally consistent. If the
provider returns `status="requires_tool"`, it must also include one or more
`ToolCallItem` values in `output_items`.

## Step 2

Construct the runtime components manually and pass your provider into `Agent`.

```python
from agentkit.agent.agent import Agent
from agentkit.agent.tool_runtime import AgentToolRuntime
from agentkit.config.schema import AgentkitConfig, RunLogConfig, ToolConfig
from agentkit.tools.registry import ToolRegistry
from agentkit.runlog import JsonlRunLogSink
from agentkit.workspace.fs import WorkspaceFS
from agentkit.workspace.layout import init_workspace_layout

config = AgentkitConfig()
config.tools = ToolConfig(allowed=[])
config.runlog = RunLogConfig(enabled=True, redact=True, max_text_chars=20000)

workspace_root = init_workspace_layout("./workspace")
fs = WorkspaceFS(workspace_root)
registry = ToolRegistry()
tool_runtime = AgentToolRuntime(registry, allowed_tools=[])
provider = EchoProvider()

agent = Agent(
    config=config,
    fs=fs,
    provider=provider,
    tool_runtime=tool_runtime,
    runlog_sink=JsonlRunLogSink(fs, config.runlog),
)
```

The config object still matters because `Agent.run` reads:

- `config.agent.system_prompt`
- `config.agent.budget`
- `config.provider` metadata for run logging and generation options
- `config.runlog`

## Step 3

Run and validate lifecycle behavior.

```python
report = agent.run("hello custom provider")
print(report.completed)
print(report.final_output)
```

## Full Example

```python
from agentkit.agent.agent import Agent
from agentkit.agent.tool_runtime import AgentToolRuntime
from agentkit.config.schema import AgentkitConfig, RunLogConfig, ToolConfig
from agentkit.llm.base import BaseLLMProvider
from agentkit.llm.types import MessageItem, StatePatch, UnifiedLLMRequest, UnifiedLLMResponse, Usage
from agentkit.tools.registry import ToolRegistry
from agentkit.runlog import JsonlRunLogSink
from agentkit.workspace.fs import WorkspaceFS
from agentkit.workspace.layout import init_workspace_layout


class EchoProvider(BaseLLMProvider):
    model = "echo-model"

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        text = ""
        for item in req.inputs:
            if isinstance(item, MessageItem) and item.role == "user":
                text = item.text
        return UnifiedLLMResponse(
            response_id="echo-1",
            status="completed",
            reason="stop",
            output_items=[MessageItem(role="assistant", text=f"echo: {text}")],
            output_text=f"echo: {text}",
            usage=Usage(),
            state_patch=StatePatch(),
            provider_name="openai",
            raw_response={"provider": "echo"},
        )


config = AgentkitConfig()
config.tools = ToolConfig(allowed=[])
config.runlog = RunLogConfig(enabled=True, redact=True, max_text_chars=20000)

root = init_workspace_layout("./workspace")
fs = WorkspaceFS(root)
agent = Agent(
    config=config,
    fs=fs,
    provider=EchoProvider(),
    tool_runtime=AgentToolRuntime(ToolRegistry(), allowed_tools=[]),
    runlog_sink=JsonlRunLogSink(fs, config.runlog),
)

report = agent.run("hello")
print(report.final_output)
```

## Expected Output

```text
echo: hello
```

## Common Pitfalls

- Expecting `create_agent(...)` or `build_provider(...)` to discover your new adapter automatically
- Returning an invalid `status` or malformed `output_items`
- Forgetting to include tool calls as `ToolCallItem` when `status="requires_tool"`
- Returning `reason="pause"` unless you also implement continuation semantics in the agent loop
- Not mapping provider errors to `ProviderError`

## Related

- [LLM Providers Concept](../concepts/llm-providers.md)
- [API: llm](../api/llm.md)
