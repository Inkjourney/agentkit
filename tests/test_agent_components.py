from __future__ import annotations

import json
import time

import pytest

from agentkit.agent.budgets import RuntimeBudget
from agentkit.agent.report import RunReport, RunStep, RunToolCall
from agentkit.agent.tool_runtime import AgentToolRuntime
from agentkit.errors import BudgetExceededError
from agentkit.llm.types import ToolCallItem, ToolResultItem, Usage
from agentkit.tools.base import FunctionTool
from agentkit.tools.registry import ToolRegistry


def _echo_tool() -> FunctionTool:
    return FunctionTool(
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


def test_runtime_budget_enforces_step_and_time_limits() -> None:
    budget = RuntimeBudget(max_steps=2, time_budget_s=5)
    budget.ensure_can_continue(0)

    with pytest.raises(BudgetExceededError, match="Step budget exceeded"):
        budget.ensure_can_continue(2)

    budget.started_monotonic = time.monotonic() - 10
    with pytest.raises(BudgetExceededError, match="Time budget exceeded"):
        budget.ensure_can_continue(1)


def test_run_report_to_dict_serializes_nested_records() -> None:
    report = RunReport(
        task="run task",
        started_at="2026-01-01T00:00:00+00:00",
        run_id="rid",
        runlog_path="logs/run.jsonl",
        status="completed",
        completed=True,
        final_output="done",
        usage=Usage(total_tokens=42),
    )
    report.steps.append(RunStep(step=0, assistant_text="thinking", tool_calls=["echo"]))
    report.tool_calls.append(
        RunToolCall(
            step=0,
            call_id="call-1",
            name="echo",
            arguments={"text": "hi"},
            is_error=False,
            output={"echo": "hi"},
            model_payload="The file draft.txt has been edited.",
            duration_ms=1.2,
        )
    )

    payload = report.to_dict()

    assert payload["task"] == "run task"
    assert payload["steps"][0]["tool_calls"] == ["echo"]
    assert payload["tool_calls"][0]["output"] == {"echo": "hi"}
    assert payload["tool_calls"][0]["model_payload"] == "The file draft.txt has been edited."
    assert payload["completed"] is True
    assert payload["final_output"] == "done"
    assert payload["usage"]["total_tokens"] == 42


def test_agent_tool_runtime_filters_schemas_and_returns_tool_result_item() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    tool_runtime = AgentToolRuntime(registry, allowed_tools=["echo"])

    schemas = tool_runtime.schemas()
    assert [schema.name for schema in schemas] == ["echo"]

    call = ToolCallItem(call_id="call-1", name="echo", arguments={"text": "hello"})
    outcome = tool_runtime.execute(call)
    model_result = tool_runtime.build_result_item(outcome)
    payload = model_result.payload

    assert outcome.is_error is False
    assert outcome.arguments == {"text": "hello"}
    assert isinstance(model_result, ToolResultItem)
    assert payload == {"output": {"echo": "hello"}}
    assert model_result.call_id == "call-1"
    assert model_result.tool_name == "echo"
    assert json.loads(model_result.output_text) == payload
    assert model_result.is_error is False


def test_agent_tool_runtime_blocks_disallowed_tools() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    tool_runtime = AgentToolRuntime(registry, allowed_tools=[])

    call = ToolCallItem(call_id="call-2", name="echo", arguments={"text": "hello"})
    outcome = tool_runtime.execute(call)
    model_result = tool_runtime.build_result_item(outcome)
    payload = model_result.payload

    assert outcome.is_error is True
    assert "not allowed" in (outcome.error or "")
    assert payload == {
        "error": {
            "code": "tool_not_allowed",
            "message": "Tool 'echo' is not allowed by the current agent config.",
        }
    }
    assert model_result.call_id == "call-2"
    assert model_result.is_error is True


def test_tool_result_item_output_text_keeps_string_payload_unwrapped() -> None:
    item = ToolResultItem(
        call_id="call-3",
        tool_name="str_replace",
        payload="The file draft.txt has been edited.",
    )

    assert item.output_text == "The file draft.txt has been edited."


def test_agent_tool_runtime_preserves_string_model_payload() -> None:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            name="describe_edit",
            description="Describe edit",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda _args: {"path": "draft.txt"},
            success_formatter=lambda output, _invocation: (
                f"The file {output['path']} has been edited."
            ),
        )
    )
    tool_runtime = AgentToolRuntime(registry, allowed_tools=["describe_edit"])

    call = ToolCallItem(call_id="call-4", name="describe_edit", arguments={})
    outcome = tool_runtime.execute(call)
    model_result = tool_runtime.build_result_item(outcome)

    assert outcome.model_payload == "The file draft.txt has been edited."
    assert model_result.payload == "The file draft.txt has been edited."
    assert model_result.output_text == "The file draft.txt has been edited."
