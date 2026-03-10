"""Tool abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from agentkit.errors import ToolError, WorkspaceError
from agentkit.tools.types import ToolInvocation, ToolModelError

ModelSuccessFormatter = Callable[[Any, ToolInvocation], Any]
ModelErrorFormatter = Callable[[Exception, ToolInvocation], Any]


class Tool(ABC):
    """Abstract base class for agent tools."""

    name: str
    description: str
    parameters: dict[str, Any]

    def schema(self) -> dict[str, Any]:
        """Return this tool's model-facing function schema.

        Returns:
            dict[str, Any]: JSON-schema style tool descriptor.
        """
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> Any:
        """Execute the tool with validated arguments.

        Args:
            arguments: Already validated tool arguments.

        Returns:
            Any: Tool-specific output payload.

        Raises:
            Exception: Implementations may raise when execution fails.
        """

    def format_output_for_model(
        self, output: Any, invocation: ToolInvocation
    ) -> Any:
        """Render a successful tool result into a model-facing payload."""
        del invocation
        return {"output": output}

    def format_error_for_model(
        self, error: Exception, invocation: ToolInvocation
    ) -> Any:
        """Render a failed tool result into a model-facing payload."""
        del invocation
        if isinstance(error, ToolModelError):
            return error.to_model_payload()
        if isinstance(error, (ToolError, WorkspaceError)):
            return {
                "error": {
                    "code": "tool_use_failed",
                    "message": str(error),
                }
            }
        return {
            "error": {
                "code": "tool_execution_failed",
                "message": f"The tool '{self.name}' failed unexpectedly.",
                "hint": "Review the arguments and retry. If the issue persists, inspect the run log.",
            }
        }


class FunctionTool(Tool):
    """Simple tool wrapper backed by a Python callable."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
        success_formatter: ModelSuccessFormatter | None = None,
        error_formatter: ModelErrorFormatter | None = None,
    ) -> None:
        """Create a callable-backed tool implementation.

        Args:
            name: Stable tool name shown to the model.
            description: Human-readable tool description.
            parameters: JSON-schema argument definition.
            handler: Callable that executes tool logic.
            success_formatter: Optional hook that converts successful tool output
                into the model-facing payload stored in conversation history.
            error_formatter: Optional hook that converts an exception into the
                model-facing payload stored in conversation history.

        Returns:
            None
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self._handler = handler
        self._success_formatter = success_formatter
        self._error_formatter = error_formatter

    def run(self, arguments: dict[str, Any]) -> Any:
        """Delegate execution to the wrapped handler.

        Args:
            arguments: Validated tool arguments.

        Returns:
            Any: Value returned by the wrapped handler.
        """
        return self._handler(arguments)

    def format_output_for_model(
        self, output: Any, invocation: ToolInvocation
    ) -> Any:
        """Delegate successful model formatting to the custom formatter when set."""
        if self._success_formatter is not None:
            return self._success_formatter(output, invocation)
        return super().format_output_for_model(output, invocation)

    def format_error_for_model(
        self, error: Exception, invocation: ToolInvocation
    ) -> Any:
        """Delegate error formatting to the custom formatter when set."""
        if self._error_formatter is not None:
            return self._error_formatter(error, invocation)
        return super().format_error_for_model(error, invocation)
