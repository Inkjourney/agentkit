from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentkit.agent.agent import Agent
from agentkit.agent.tool_runtime import AgentToolRuntime
from agentkit.config.schema import (
    AgentConfig,
    AgentkitConfig,
    BudgetConfig,
    ProviderConfig,
    RunLogConfig,
    ToolConfig,
)
from agentkit.errors import ProviderError
from agentkit.llm.base import BaseLLMProvider
from agentkit.llm.types import (
    ConversationItem,
    MessageItem,
    StatePatch,
    ToolCallItem,
    ToolResultItem,
    UnifiedLLMRequest,
    UnifiedLLMResponse,
    Usage,
)
from agentkit.tools.base import FunctionTool
from agentkit.tools.registry import ToolRegistry
from agentkit.runlog import JsonlRunLogSink
from agentkit.workspace.fs import WorkspaceFS


class ScriptedProvider(BaseLLMProvider):
    def __init__(self, outputs: list[UnifiedLLMResponse | Exception]) -> None:
        self.model = "fake-model"
        self._outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def generate(self, req: UnifiedLLMRequest) -> UnifiedLLMResponse:
        self.calls.append(
            {
                "history": list(req.state.history),
                "inputs": list(req.inputs),
                "instructions": req.instructions,
                "tools": list(req.tools),
                "options": req.options,
            }
        )
        if not self._outputs:
            raise RuntimeError("No scripted provider outputs left.")
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def _build_agent(
    fs: WorkspaceFS, provider: BaseLLMProvider, *, max_steps: int = 3
) -> Agent:
    config = AgentkitConfig(
        provider=ProviderConfig(
            kind="openai",
            model="fake-model",
            openai_api_variant="responses",
            conversation_mode="auto",
        ),
        agent=AgentConfig(
            system_prompt="test-system-prompt",
            budget=BudgetConfig(max_steps=max_steps, time_budget_s=60, max_input_chars=5000),
        ),
        tools=ToolConfig(allowed=["echo"]),
        runlog=RunLogConfig(enabled=True, redact=True, max_text_chars=2000),
    )

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
    return Agent(
        config=config,
        fs=fs,
        provider=provider,
        tool_runtime=AgentToolRuntime(registry, allowed_tools=["echo"]),
        runlog_sink=JsonlRunLogSink(fs, config.runlog),
    )


def _items_kinds(items: list[ConversationItem]) -> list[str]:
    kinds: list[str] = []
    for item in items:
        if isinstance(item, MessageItem):
            kinds.append(f"message:{item.role}")
        elif isinstance(item, ToolCallItem):
            kinds.append("tool_call")
        elif isinstance(item, ToolResultItem):
            kinds.append("tool_result")
        else:
            kinds.append("reasoning")
    return kinds


def _latest_runlog_rows(workspace_fs: WorkspaceFS) -> list[dict[str, Any]]:
    runlog_files = sorted((workspace_fs.root / "logs").glob("run_*.jsonl"))
    assert runlog_files, "expected a run log file to be created"
    return [
        json.loads(line)
        for line in runlog_files[-1].read_text(encoding="utf-8").splitlines()
    ]


def test_agent_run_success_flow_and_state_transaction_order(workspace_fs: WorkspaceFS) -> None:
    provider = ScriptedProvider(
        [
            UnifiedLLMResponse(
                response_id="resp-1",
                status="requires_tool",
                reason="tool_call",
                output_items=[
                    MessageItem(role="assistant", text="I will call a tool"),
                    ToolCallItem(call_id="call-1", name="echo", arguments={"text": "hello"}),
                ],
                output_text="I will call a tool",
                usage=Usage(
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    reasoning_tokens=2,
                    cache_read_tokens=1,
                ),
                state_patch=StatePatch(new_provider_cursor="resp-1"),
                provider_name="openai",
                raw_response={"id": "resp-1"},
            ),
            UnifiedLLMResponse(
                response_id="resp-2",
                status="completed",
                reason="stop",
                output_items=[MessageItem(role="assistant", text="final answer")],
                output_text="final answer",
                usage=Usage(
                    input_tokens=7,
                    output_tokens=3,
                    total_tokens=10,
                    reasoning_tokens=1,
                    cache_write_tokens=4,
                ),
                state_patch=StatePatch(new_provider_cursor="resp-2"),
                provider_name="openai",
                raw_response={"id": "resp-2"},
            ),
        ]
    )
    agent = _build_agent(workspace_fs, provider)

    report = agent.run("say hello")

    assert report.completed is True
    assert report.final_output == "final answer"
    assert report.status == "completed"
    assert report.usage.input_tokens == 17
    assert report.usage.output_tokens == 8
    assert report.usage.total_tokens == 25
    assert report.usage.reasoning_tokens == 3
    assert report.usage.cache_read_tokens == 1
    assert report.usage.cache_write_tokens == 4
    assert len(report.steps) == 2
    assert len(report.tool_calls) == 1
    assert report.tool_calls[0].name == "echo"
    assert report.tool_calls[0].is_error is False
    assert report.tool_calls[0].output == {"echo": "hello"}
    assert report.tool_calls[0].model_payload == {"output": {"echo": "hello"}}

    assert len(provider.calls) == 2

    # 1st call: no pre-mutated history, only user input in req.inputs
    assert provider.calls[0]["history"] == []
    assert _items_kinds(provider.calls[0]["inputs"]) == ["message:user"]

    # 2nd call: history has turn-1 inputs + outputs; inputs has tool_result only
    assert _items_kinds(provider.calls[1]["history"]) == [
        "message:user",
        "message:assistant",
        "tool_call",
    ]
    assert _items_kinds(provider.calls[1]["inputs"]) == ["tool_result"]

    runlog_path = Path(report.runlog_path or "")
    assert runlog_path.exists()
    rows = [json.loads(line) for line in runlog_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["kind"] == "run_started"
    assert rows[0]["payload"]["context"]["model"] == "fake-model"
    assert rows[0]["payload"]["context"]["provider"] == "openai"
    assert rows[0]["payload"]["context"]["instructions"] == "test-system-prompt"
    assert rows[0]["payload"]["context"]["tools"][0]["name"] == "echo"
    assert any(row["kind"] == "run_finished" for row in rows)
    assert any(
        row["kind"] == "run_finished" and row["payload"]["status"] == "completed"
        for row in rows
    )
    assert any(
        row["kind"] == "run_finished" and row["payload"]["usage"]["total_tokens"] == 25
        for row in rows
    )
    first_model_row = next(row for row in rows if row["kind"] == "model_responded")
    assert "model" not in first_model_row["payload"]
    assert "request_snapshot" not in first_model_row["payload"]
    assert "response_snapshot" not in first_model_row["payload"]
    assert first_model_row["payload"]["request"]["inputs"][0]["kind"] == "message"
    assert first_model_row["payload"]["requested_tools"] == [
        {
            "kind": "tool_call",
            "call_id": "call-1",
            "name": "echo",
            "arguments": {"text": "hello"},
            "raw_arguments": None,
        }
    ]
    assert first_model_row["payload"]["response"]["response_id"] == "resp-1"
    tool_row = next(row for row in rows if row["kind"] == "tool_executed")
    assert tool_row["payload"]["call_id"] == "call-1"
    assert tool_row["payload"]["is_error"] is False
    assert tool_row["payload"]["model_payload"] == {"output": {"echo": "hello"}}


def test_agent_run_marks_runlog_as_failed_on_exception(workspace_fs: WorkspaceFS) -> None:
    provider = ScriptedProvider([RuntimeError("provider exploded")])
    agent = _build_agent(workspace_fs, provider)

    with pytest.raises(RuntimeError, match="provider exploded"):
        agent.run("trigger failure")

    rows = _latest_runlog_rows(workspace_fs)
    assert rows[-1]["kind"] == "run_finished"
    assert rows[-1]["payload"]["status"] == "failed"
    assert rows[-1]["payload"]["error_type"] == "RuntimeError"
    assert rows[-1]["payload"]["error_message"] == "provider exploded"
    assert rows[-1]["payload"]["usage"]["total_tokens"] is None


def test_agent_run_returns_blocked_terminal_status(workspace_fs: WorkspaceFS) -> None:
    provider = ScriptedProvider(
        [
            UnifiedLLMResponse(
                response_id="resp-blocked",
                status="blocked",
                reason="refusal",
                output_items=[MessageItem(role="assistant", text="cannot comply")],
                output_text="cannot comply",
                usage=Usage(),
                state_patch=StatePatch(),
                provider_name="openai",
                raw_response={"id": "resp-blocked"},
            )
        ]
    )
    agent = _build_agent(workspace_fs, provider)

    report = agent.run("blocked request")

    assert report.status == "blocked"
    assert report.completed is False
    assert report.final_output == "cannot comply"
    assert report.reason == "refusal"
    assert len(provider.calls) == 1

    rows = _latest_runlog_rows(workspace_fs)
    assert rows[-1]["kind"] == "run_finished"
    assert rows[-1]["payload"]["status"] == "blocked"
    assert rows[-1]["payload"]["reason"] == "refusal"


def test_agent_run_returns_incomplete_terminal_status(workspace_fs: WorkspaceFS) -> None:
    provider = ScriptedProvider(
        [
            UnifiedLLMResponse(
                response_id="resp-incomplete",
                status="incomplete",
                reason="max_tokens",
                output_items=[MessageItem(role="assistant", text="partial answer")],
                output_text="partial answer",
                usage=Usage(),
                state_patch=StatePatch(),
                provider_name="openai",
                raw_response={"id": "resp-incomplete"},
            )
        ]
    )
    agent = _build_agent(workspace_fs, provider)

    report = agent.run("long request")

    assert report.status == "incomplete"
    assert report.completed is False
    assert report.final_output == "partial answer"
    assert report.reason == "max_tokens"
    assert len(provider.calls) == 1

    rows = _latest_runlog_rows(workspace_fs)
    assert rows[-1]["kind"] == "run_finished"
    assert rows[-1]["payload"]["status"] == "incomplete"
    assert rows[-1]["payload"]["reason"] == "max_tokens"


def test_agent_run_fails_when_requires_tool_has_no_tool_calls(
    workspace_fs: WorkspaceFS,
) -> None:
    provider = ScriptedProvider(
        [
            UnifiedLLMResponse(
                response_id="resp-missing-tool-call",
                status="requires_tool",
                reason="tool_call",
                output_items=[MessageItem(role="assistant", text="I need a tool")],
                output_text="I need a tool",
                usage=Usage(),
                state_patch=StatePatch(),
                provider_name="openai",
                raw_response={"id": "resp-missing-tool-call"},
            )
        ]
    )
    agent = _build_agent(workspace_fs, provider)

    with pytest.raises(
        ProviderError, match="requested tool execution but returned no tool calls"
    ):
        agent.run("broken tool request")

    rows = _latest_runlog_rows(workspace_fs)
    assert rows[-1]["kind"] == "run_finished"
    assert rows[-1]["payload"]["status"] == "failed"
    assert rows[-1]["payload"]["reason"] == "tool_call"
    assert rows[-1]["payload"]["final_output"] == "I need a tool"


def test_agent_run_fails_when_pause_continuation_is_not_supported(
    workspace_fs: WorkspaceFS,
) -> None:
    provider = ScriptedProvider(
        [
            UnifiedLLMResponse(
                response_id="resp-pause",
                status="incomplete",
                reason="pause",
                output_items=[MessageItem(role="assistant", text="hold on")],
                output_text="hold on",
                usage=Usage(),
                state_patch=StatePatch(new_provider_cursor="resp-pause"),
                provider_name="openai",
                raw_response={"id": "resp-pause"},
            )
        ]
    )
    agent = _build_agent(workspace_fs, provider)

    with pytest.raises(
        ProviderError,
        match="Automatic continuation is not implemented",
    ):
        agent.run("pause request")

    rows = _latest_runlog_rows(workspace_fs)
    assert rows[-1]["kind"] == "run_finished"
    assert rows[-1]["payload"]["status"] == "failed"
    assert rows[-1]["payload"]["reason"] == "pause"
    assert rows[-1]["payload"]["final_output"] == "hold on"
