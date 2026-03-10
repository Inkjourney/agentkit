"""Tool-related invocation and outcome types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolModelError(Exception):
    """Tool-defined model-facing error payload.

    Tool authors can raise this directly from custom tools when they want the model
    to receive a stable, structured error description instead of a raw exception
    string.
    """

    code: str
    message: str
    hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize the underlying ``Exception`` with the human-readable message."""
        Exception.__init__(self, self.message)

    def __str__(self) -> str:
        """Return the message so generic exception handling stays readable."""
        return self.message

    def to_model_payload(self) -> dict[str, Any]:
        """Serialize the structured error into the canonical model payload shape."""
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.hint:
            error["hint"] = self.hint
        if self.details:
            error["details"] = dict(self.details)
        return {"error": error}


@dataclass(slots=True)
class ToolInvocation:
    """Structured request to execute one tool.

    Attributes:
        name: Tool name.
        arguments: Parsed argument mapping supplied by the caller.
        call_id: Optional provider-assigned tool call identifier.
    """

    name: str
    arguments: Any
    call_id: str | None = None


@dataclass(slots=True)
class ToolCallOutcome:
    """Canonical outcome of a single tool call.

    Attributes:
        call_id: Optional provider-assigned tool call identifier.
        name: Tool name.
        arguments: Validated argument mapping when available.
        output: Successful output payload.
        error: Failure message when execution failed.
        model_payload: Model-facing payload derived from tool-specific success/error
            formatting hooks.
        duration_ms: Execution latency in milliseconds.
    """

    call_id: str | None
    name: str
    arguments: dict[str, Any]
    output: Any = None
    error: str | None = None
    model_payload: Any = None
    duration_ms: float | None = None

    @property
    def is_error(self) -> bool:
        """Return ``True`` when the tool finished with an error message."""
        return self.error is not None

    def to_event_payload(self) -> dict[str, Any]:
        """Serialize the stable run-event payload for this tool outcome."""
        return {
            "call_id": self.call_id,
            "name": self.name,
            "is_error": self.is_error,
            "arguments": dict(self.arguments),
            "output": self.output,
            "error": self.error,
            "model_payload": self.model_payload,
            "duration_ms": self.duration_ms,
        }
