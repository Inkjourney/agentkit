"""Tool runtime filtering and model-call bridging."""

from __future__ import annotations

import json
from typing import Sequence

from agentkit.llm.types import ToolCallItem, ToolResultItem, UnifiedToolSpec
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.types import ToolCallOutcome, ToolInvocation


class AgentToolRuntime:
    """Expose allowed tool schemas and execute tool calls for the agent loop."""

    def __init__(
        self, registry: ToolRegistry, allowed_tools: Sequence[str] | None = None
    ) -> None:
        """Create a runtime view over the registry filtered by agent config."""
        self._registry = registry
        if allowed_tools is None:
            self._allowed = set(registry.list_names())
        else:
            self._allowed = set(allowed_tools)

    def schemas(self) -> list[UnifiedToolSpec]:
        """Return schemas for tools currently allowed to the agent."""
        raw_schemas = self._registry.schemas(self._allowed)
        return [
            UnifiedToolSpec(
                name=str(schema.get("name") or ""),
                description=str(schema.get("description") or ""),
                parameters=dict(schema.get("parameters") or {}),
            )
            for schema in raw_schemas
        ]

    def execute(self, call: ToolCallItem) -> ToolCallOutcome:
        """Execute one tool call and return the canonical outcome."""
        if call.name not in self._allowed:
            return ToolCallOutcome(
                call_id=call.call_id,
                name=call.name,
                arguments=dict(call.arguments),
                error=f"Tool not allowed by current agent config: {call.name}",
                model_payload={
                    "error": {
                        "code": "tool_not_allowed",
                        "message": f"Tool '{call.name}' is not allowed by the current agent config.",
                    }
                },
            )
        return self._registry.execute(
            ToolInvocation(
                name=call.name,
                arguments=call.arguments,
                call_id=call.call_id,
            )
        )

    def build_result_item(self, outcome: ToolCallOutcome) -> ToolResultItem:
        """Build the model-facing transcript item for a completed tool call."""
        payload = outcome.model_payload
        if payload is None:
            if outcome.is_error:
                payload = {"error": {"message": outcome.error or "Tool execution failed."}}
            else:
                payload = {"output": outcome.output}
        # Round-trip through JSON so provider adapters only ever see plain Python
        # primitives, not custom mapping/list subclasses returned by a tool.
        payload = json.loads(json.dumps(payload, ensure_ascii=False))
        return ToolResultItem(
            call_id=outcome.call_id or "",
            tool_name=outcome.name,
            payload=payload,
            is_error=outcome.is_error,
        )
