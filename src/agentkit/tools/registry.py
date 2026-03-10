"""Tool registration, validation, and execution."""

from __future__ import annotations

import time
from typing import Any, Iterable

from agentkit.errors import ToolError
from agentkit.tools.base import Tool
from agentkit.tools.types import ToolCallOutcome, ToolInvocation, ToolModelError

_JSON_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list, tuple),
}


class ToolRegistry:
    """Store, validate, and execute named tools."""

    def __init__(self) -> None:
        """Initialize an empty tool registry.

        Returns:
            None
        """
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a single tool by name.

        Args:
            tool: Tool instance to add.

        Returns:
            None

        Raises:
            agentkit.errors.ToolError: If tool name is invalid or duplicated.
        """
        if "." in tool.name:
            raise ToolError(f"Tool name cannot contain '.': {tool.name}")
        if tool.name in self._tools:
            raise ToolError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def register_many(self, tools: Iterable[Tool]) -> None:
        """Register multiple tools.

        Args:
            tools: Iterable of tools to register.

        Returns:
            None

        Raises:
            agentkit.errors.ToolError: If any tool fails validation or duplicates an
                existing name.
        """
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool:
        """Retrieve a registered tool by name.

        Args:
            name: Tool name.

        Returns:
            Tool: Registered tool instance.

        Raises:
            agentkit.errors.ToolError: If the tool is not registered.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Tool not found: {name}")
        return tool

    def list_names(self) -> list[str]:
        """Return all registered tool names in sorted order.

        Returns:
            list[str]: Sorted tool names.
        """
        return sorted(self._tools.keys())

    def schemas(self, allowed: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Build model-facing schemas for registered tools.

        Args:
            allowed: Optional iterable of allowed tool names.

        Returns:
            list[dict[str, Any]]: Tool schema dictionaries.
        """
        if allowed is None:
            names = self.list_names()
        else:
            names = [name for name in allowed if name in self._tools]
        return [self._tools[name].schema() for name in names]

    def execute(self, invocation: ToolInvocation) -> ToolCallOutcome:
        """Execute a tool and wrap success/failure in ``ToolCallOutcome``.

        Args:
            invocation: Tool invocation including name, arguments, and optional
                correlation id.

        Returns:
            ToolCallOutcome: Outcome including arguments, latency, and errors.
        """
        start = time.perf_counter()
        tool: Tool | None = None
        try:
            tool = self.get(invocation.name)
            self._validate_arguments(tool.parameters, invocation.arguments)
            output = tool.run(invocation.arguments)
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolCallOutcome(
                call_id=invocation.call_id,
                name=invocation.name,
                arguments=self._normalize_arguments(invocation.arguments),
                output=output,
                model_payload=self._normalize_model_payload(
                    tool.format_output_for_model(output, invocation),
                    fallback={"output": output},
                ),
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolCallOutcome(
                call_id=invocation.call_id,
                name=invocation.name,
                arguments=self._normalize_arguments(invocation.arguments),
                error=str(exc),
                model_payload=self._format_error_payload(
                    exc,
                    invocation=invocation,
                    tool=tool,
                ),
                duration_ms=duration_ms,
            )

    def _normalize_arguments(self, arguments: Any) -> dict[str, Any]:
        """Return a defensive copy of invocation arguments when they are object-like."""
        if isinstance(arguments, dict):
            return dict(arguments)
        return {}

    def _normalize_model_payload(self, payload: Any, *, fallback: Any) -> Any:
        """Normalize formatter output into a stable payload shape."""
        if payload is None:
            return fallback
        if isinstance(payload, dict):
            return dict(payload)
        return payload

    def _format_error_payload(
        self,
        exc: Exception,
        *,
        invocation: ToolInvocation,
        tool: Tool | None,
    ) -> Any:
        """Build the model-facing error payload for execution or registry failures."""
        fallback = {
            "error": {
                "code": "tool_execution_failed",
                "message": f"The tool '{invocation.name}' failed unexpectedly.",
            }
        }
        if tool is not None:
            payload = tool.format_error_for_model(exc, invocation)
            return self._normalize_model_payload(payload, fallback=fallback)
        return self._format_registry_error(exc, invocation)

    def _format_registry_error(
        self, exc: Exception, invocation: ToolInvocation
    ) -> dict[str, Any]:
        """Translate registry/validation failures into stable error codes."""
        if isinstance(exc, ToolModelError):
            return exc.to_model_payload()
        if isinstance(exc, ToolError):
            # Keep these codes stable so providers and downstream tooling can rely on
            # them without parsing free-form exception strings.
            message = str(exc)
            if message.startswith("Tool not found: "):
                return {
                    "error": {
                        "code": "tool_not_found",
                        "message": f"Tool '{invocation.name}' is not registered.",
                    }
                }
            if message == "Tool arguments must be an object.":
                return {
                    "error": {
                        "code": "invalid_arguments",
                        "message": "Tool arguments must be a JSON object.",
                    }
                }
            if message.startswith("Missing required argument: "):
                key = message.removeprefix("Missing required argument: ")
                return {
                    "error": {
                        "code": "missing_argument",
                        "message": f"Missing required argument '{key}'.",
                        "hint": f"Call the tool again and include '{key}'.",
                    }
                }
            if message.startswith("Unexpected argument: "):
                key = message.removeprefix("Unexpected argument: ")
                return {
                    "error": {
                        "code": "unexpected_argument",
                        "message": f"Argument '{key}' is not accepted by this tool.",
                    }
                }
            if message.startswith("Invalid type for '"):
                return {
                    "error": {
                        "code": "invalid_argument_type",
                        "message": message,
                    }
                }
            return {
                "error": {
                    "code": "tool_invocation_invalid",
                    "message": message,
                }
            }
        return {
            "error": {
                "code": "tool_execution_failed",
                "message": f"The tool '{invocation.name}' failed unexpectedly.",
            }
        }

    def _validate_arguments(
        self, schema: dict[str, Any], arguments: dict[str, Any]
    ) -> None:
        """Validate runtime arguments against a JSON-schema subset.

        Args:
            schema: Tool parameter schema.
            arguments: Runtime argument object.

        Returns:
            None

        Raises:
            agentkit.errors.ToolError: If required keys are missing, unexpected keys
                are disallowed, or value types mismatch declared schema types.
        """
        if not isinstance(arguments, dict):
            raise ToolError("Tool arguments must be an object.")

        required = schema.get("required", [])
        for key in required:
            if key not in arguments:
                raise ToolError(f"Missing required argument: {key}")

        properties = schema.get("properties", {})
        additional_allowed = schema.get("additionalProperties", True)

        for key, value in arguments.items():
            if key not in properties:
                if additional_allowed is False:
                    raise ToolError(f"Unexpected argument: {key}")
                continue

            expected_type = properties[key].get("type")
            if expected_type is None:
                continue
            py_types = _JSON_TYPE_MAP.get(expected_type)
            if py_types and not isinstance(value, py_types):
                raise ToolError(
                    f"Invalid type for '{key}': expected {expected_type}, got {type(value).__name__}"
                )
