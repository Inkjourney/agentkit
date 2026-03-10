from __future__ import annotations

import pytest

from agentkit.errors import ToolError
from agentkit.tools.base import FunctionTool
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.types import ToolCallOutcome, ToolInvocation, ToolModelError


def _make_echo_tool(name: str = "echo") -> FunctionTool:
    return FunctionTool(
        name=name,
        description="Echo text",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=lambda args: args["text"],
    )


def test_register_and_get_tool() -> None:
    registry = ToolRegistry()
    tool = _make_echo_tool()

    registry.register(tool)

    assert registry.get("echo") is tool
    assert registry.list_names() == ["echo"]


def test_register_rejects_duplicate_or_invalid_name() -> None:
    registry = ToolRegistry()
    registry.register(_make_echo_tool())

    with pytest.raises(ToolError, match="Duplicate tool name"):
        registry.register(_make_echo_tool())

    with pytest.raises(ToolError, match="cannot contain"):
        registry.register(_make_echo_tool(name="invalid.name"))


def test_get_raises_for_missing_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolError, match="Tool not found"):
        registry.get("missing")


def test_schemas_support_allowlist_and_sorted_names() -> None:
    registry = ToolRegistry()
    registry.register_many([_make_echo_tool("b"), _make_echo_tool("a")])

    assert [item["name"] for item in registry.schemas()] == ["a", "b"]
    assert [item["name"] for item in registry.schemas(["b", "missing"])] == ["b"]


def test_execute_success_and_validation_failures() -> None:
    registry = ToolRegistry()
    registry.register(_make_echo_tool())

    outcome = registry.execute(ToolInvocation(name="echo", arguments={"text": "hello"}))
    assert outcome.is_error is False
    assert outcome.output == "hello"
    assert outcome.duration_ms is not None and outcome.duration_ms >= 0

    missing = registry.execute(ToolInvocation(name="echo", arguments={}))
    assert missing.is_error is True
    assert "Missing required argument" in (missing.error or "")

    unexpected = registry.execute(
        ToolInvocation(name="echo", arguments={"text": "hello", "extra": 1})
    )
    assert unexpected.is_error is True
    assert "Unexpected argument" in (unexpected.error or "")

    wrong_type = registry.execute(
        ToolInvocation(name="echo", arguments={"text": 123})  # type: ignore[arg-type]
    )
    assert wrong_type.is_error is True
    assert "Invalid type" in (wrong_type.error or "")

    not_object = registry.execute(
        ToolInvocation(name="echo", arguments=["not-an-object"])  # type: ignore[arg-type]
    )
    assert not_object.is_error is True
    assert "must be an object" in (not_object.error or "")


def test_execute_handles_unknown_tool_and_tool_runtime_error() -> None:
    registry = ToolRegistry()

    missing = registry.execute(ToolInvocation(name="missing", arguments={}))
    assert missing.is_error is True
    assert "Tool not found" in (missing.error or "")

    broken_tool = FunctionTool(
        name="broken",
        description="Always fails",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    registry.register(broken_tool)
    failed = registry.execute(ToolInvocation(name="broken", arguments={}))
    assert failed.is_error is True
    assert failed.error == "boom"


def test_execute_uses_tool_defined_model_error_payload() -> None:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            name="custom",
            description="Custom tool",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda _args: (_ for _ in ()).throw(
                ToolModelError(
                    code="resource_not_ready",
                    message="The custom resource is not ready yet.",
                    hint="Wait for initialization to complete, then retry.",
                    details={"resource": "demo"},
                )
            ),
        )
    )

    outcome = registry.execute(ToolInvocation(name="custom", arguments={}))

    assert outcome.is_error is True
    assert outcome.error == "The custom resource is not ready yet."
    assert outcome.model_payload == {
        "error": {
            "code": "resource_not_ready",
            "message": "The custom resource is not ready yet.",
            "hint": "Wait for initialization to complete, then retry.",
            "details": {"resource": "demo"},
        }
    }


def test_execute_uses_custom_success_formatter() -> None:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            name="slugify",
            description="Slugify text",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=lambda args: {"slug": args["text"].strip().lower().replace(" ", "-")},
            success_formatter=lambda output, invocation: {
                "result": output,
                "summary": f"Created slug for {invocation.arguments['text']!r}.",
            },
        )
    )

    outcome = registry.execute(
        ToolInvocation(name="slugify", arguments={"text": "Agent Kit Docs"})
    )

    assert outcome.is_error is False
    assert outcome.output == {"slug": "agent-kit-docs"}
    assert outcome.model_payload == {
        "result": {"slug": "agent-kit-docs"},
        "summary": "Created slug for 'Agent Kit Docs'.",
    }


def test_execute_allows_string_success_formatter() -> None:
    registry = ToolRegistry()
    registry.register(
        FunctionTool(
            name="edit_notice",
            description="Describe edit result",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda _args: {"path": "draft.txt"},
            success_formatter=lambda output, _invocation: (
                f"The file {output['path']} has been edited."
            ),
        )
    )

    outcome = registry.execute(ToolInvocation(name="edit_notice", arguments={}))

    assert outcome.is_error is False
    assert outcome.output == {"path": "draft.txt"}
    assert outcome.model_payload == "The file draft.txt has been edited."


def test_tool_call_outcome_to_event_payload_keeps_stable_schema() -> None:
    outcome = ToolCallOutcome(
        call_id="call-1",
        name="echo",
        arguments={"text": "hello"},
        output={"echo": "hello"},
        model_payload={"result": {"echo": "hello"}},
        duration_ms=12.5,
    )

    assert outcome.to_event_payload() == {
        "call_id": "call-1",
        "name": "echo",
        "is_error": False,
        "arguments": {"text": "hello"},
        "output": {"echo": "hello"},
        "error": None,
        "model_payload": {"result": {"echo": "hello"}},
        "duration_ms": 12.5,
    }
