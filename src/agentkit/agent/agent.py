"""Agent core loop: model inference <-> tool execution."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from agentkit.agent.budgets import RuntimeBudget
from agentkit.agent.report import RunReport, RunReportProjector
from agentkit.agent.tool_runtime import AgentToolRuntime
from agentkit.config.schema import AgentkitConfig
from agentkit.errors import ProviderError
from agentkit.llm.base import BaseLLMProvider
from agentkit.llm.factory import build_provider
from agentkit.llm.types import (
    ConversationItem,
    ConversationState,
    GenerationOptions,
    MessageItem,
    ToolCallItem,
    ToolResultItem,
    UnifiedLLMRequest,
    Usage,
)
from agentkit.llm.usage import merge_usage, usage_to_payload
from agentkit.runlog import JsonlRunLogSink
from agentkit.tools.loader import load_tools_from_entries, load_tools_from_library
from agentkit.tools.registry import ToolRegistry
from agentkit.runlog.recorder import RunRecorder
from agentkit.workspace.fs import WorkspaceFS
from agentkit.workspace.layout import init_workspace_layout


class Agent:
    """Coordinate model calls, tool execution, and event-driven projections.

    The Agent orchestrates the core loop:

        User Task
            ↓
        Model Inference
            ↓
        Tool Calls (optional)
            ↓
        Tool Execution
            ↓
        Model Continues
            ↓
        Final Result

    All events are recorded and projected into a RunReport and optional run logs.
    """

    def __init__(
        self,
        *,
        config: AgentkitConfig,
        fs: WorkspaceFS,
        provider: BaseLLMProvider,
        tool_runtime: AgentToolRuntime,
        runlog_sink: JsonlRunLogSink,
    ) -> None:
        self.config = config
        self.fs = fs
        self.provider = provider
        self.tool_runtime = tool_runtime
        self.runlog_sink = runlog_sink

    @classmethod
    def from_config(cls, config: AgentkitConfig) -> "Agent":
        """Build an Agent from validated configuration."""

        # Initialize workspace directory layout
        workspace_root = init_workspace_layout(config.workspace.root)
        fs = WorkspaceFS(workspace_root)

        # Build the configured LLM provider
        provider = build_provider(config.provider)

        # Load built-in tools plus any configured external tool entries.
        registry = ToolRegistry()
        registry.register_many(load_tools_from_library(fs))
        registry.register_many(load_tools_from_entries(config.tools.entries, fs))

        # Create tool runtime with allowlist filtering
        tool_runtime = AgentToolRuntime(registry, config.tools.allowed)

        # Initialize run logging
        runlog_sink = JsonlRunLogSink(fs, config.runlog)

        return cls(
            config=config,
            fs=fs,
            provider=provider,
            tool_runtime=tool_runtime,
            runlog_sink=runlog_sink,
        )

    def run(self, task: str) -> RunReport:
        """Execute the full model-tool loop for a single task.

        The run proceeds as:

        1. Initialize runtime state
        2. Call model
        3. Execute tools if requested
        4. Feed tool results back to model
        5. Repeat until model completes
        6. Produce final RunReport
        """

        # Project events into both a final report and the optional run log.
        report_projector = RunReportProjector()
        recorder = RunRecorder(sinks=[report_projector, self.runlog_sink])

        tool_specs = self.tool_runtime.schemas()  # tool schemas exposed to the LLM
        instructions = self.config.agent.system_prompt  # system prompt
        options = GenerationOptions(
            temperature=self.config.provider.temperature,
            reasoning_effort=self.config.provider.reasoning_effort,
            thinking_enabled=self.config.provider.enable_thinking,
        )  # generation parameters

        # Start run recording
        run_id = recorder.start_run(
            task=task,
            context={
                "provider": self.config.provider.kind,
                "model": self.config.provider.model,
                "conversation_mode": self.config.provider.conversation_mode,
                "instructions": instructions,
                "tools": [asdict(tool) for tool in tool_specs],
                "options": asdict(options),
            },
        )

        # Runtime guardrails
        budget = RuntimeBudget(
            max_steps=self.config.agent.budget.max_steps,
            time_budget_s=self.config.agent.budget.time_budget_s,
        )

        # Conversation state holds full chat history
        state = ConversationState(mode=self.config.provider.conversation_mode)

        # Inputs for the next model turn
        next_inputs: list[ConversationItem] = [MessageItem(role="user", text=task)]

        step = 0
        run_closed = False
        model_step_count = 0
        tool_call_count = 0
        aggregate_usage = Usage()

        # Track last response for better error reporting
        last_response_reason: str | None = None
        last_response_output = ""

        try:
            while True:
                # Ensure execution stays within configured limits
                budget.ensure_can_continue(step)

                # Build the unified LLM request
                req = UnifiedLLMRequest(
                    provider=self.config.provider.kind,
                    model=self.config.provider.model,
                    state=state,
                    inputs=list(next_inputs),
                    instructions=instructions,
                    tools=tool_specs,
                    options=options,
                )

                # Call LLM provider
                call_start = time.perf_counter()
                response = self.provider.generate(req)
                call_ms = (time.perf_counter() - call_start) * 1000

                last_response_reason = response.reason
                last_response_output = response.output_text
                merge_usage(aggregate_usage, response.usage)

                # Update conversation history
                state.history.extend(req.inputs)
                state.history.extend(response.output_items)

                # Apply provider state patches (cursor updates etc.)
                if response.state_patch.new_provider_cursor is not None:
                    state.provider_cursor = response.state_patch.new_provider_cursor

                if response.state_patch.provider_meta_patch:
                    state.provider_meta.update(response.state_patch.provider_meta_patch)

                # Record model response event
                recorder.emit(
                    "model_responded",
                    step=step,
                    payload={
                        "status": response.status,
                        "reason": response.reason,
                        "output_text": response.output_text,
                        "duration_ms": call_ms,
                        "requested_tools": [
                            self._serialize_item(call) for call in response.tool_calls
                        ],
                        "request": {
                            "state_cursor": req.state.provider_cursor,
                            "inputs": [self._serialize_item(i) for i in req.inputs],
                        },
                        "response": {
                            "response_id": response.response_id,
                            "output_items": [
                                self._serialize_item(i) for i in response.output_items
                            ],
                            "usage": asdict(response.usage),
                            "state_patch": asdict(response.state_patch),
                            "raw_response": response.raw_response,
                        },
                    },
                )

                model_step_count += 1
                next_inputs = []

                # Branch based on provider response status
                match response.status:
                    case "requires_tool":
                        # Model requested tool execution

                        if not response.tool_calls:
                            raise ProviderError(
                                "Model turn requested tool execution but returned no tool calls."
                            )

                        # Execute tools and collect results
                        for call in response.tool_calls:
                            outcome = self.tool_runtime.execute(call)

                            # Tool result becomes next model input
                            next_inputs.append(
                                self.tool_runtime.build_result_item(outcome)
                            )

                            # Record tool execution
                            recorder.emit(
                                "tool_executed",
                                step=step,
                                payload=outcome.to_event_payload(),
                            )

                            tool_call_count += 1

                        step += 1
                        continue

                    case "completed" | "blocked" | "incomplete":
                        # Run finished (successfully or otherwise)

                        if response.reason == "pause":
                            raise ProviderError(
                                "Model turn paused with reason=pause. Automatic continuation is not implemented."
                            )

                        recorder.end_run(
                            status=response.status,
                            payload={
                                "reason": response.reason,
                                "step_count": model_step_count,
                                "tool_call_count": tool_call_count,
                                "final_output": response.output_text,
                                "usage": usage_to_payload(aggregate_usage),
                            },
                        )

                        run_closed = True
                        break

                    case "failed":
                        # Provider explicitly reported failure
                        raise ProviderError(
                            f"Model turn failed with reason={response.reason}."
                        )

                    case _:
                        # Unknown response status
                        raise ProviderError(
                            f"Model turn returned unsupported status={response.status!r}."
                        )

        except Exception as exc:
            # Ensure failed runs are properly recorded
            if not run_closed:
                payload = {
                    "step_count": model_step_count,
                    "tool_call_count": tool_call_count,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }

                if last_response_reason is not None:
                    payload["reason"] = last_response_reason

                if last_response_output:
                    payload["final_output"] = last_response_output

                payload["usage"] = usage_to_payload(aggregate_usage)

                recorder.end_run(
                    status="failed",
                    payload=payload,
                )

            raise

        # Build final report from recorded events
        report = report_projector.build(
            runlog_path=(
                str(self.runlog_sink.runlog_path_for_run(run_id))
                if self.runlog_sink.enabled
                else None
            )
        )

        # Safety check to ensure run IDs match
        if report.run_id != run_id:
            raise RuntimeError(
                "Run report projection mismatch: run_id changed during recording."
            )

        return report

    def _serialize_item(self, item: ConversationItem) -> dict[str, Any]:
        """Convert a conversation item into a run-log friendly structure.

        This avoids leaking internal objects into logs and ensures JSON-safe output.
        """

        if isinstance(item, MessageItem):
            return {"kind": "message", "role": item.role, "text": item.text}

        if isinstance(item, ToolCallItem):
            return {
                "kind": "tool_call",
                "call_id": item.call_id,
                "name": item.name,
                "arguments": item.arguments,
                "raw_arguments": item.raw_arguments,
            }

        if isinstance(item, ToolResultItem):
            return {
                "kind": "tool_result",
                "call_id": item.call_id,
                "tool_name": item.tool_name,
                "payload": item.payload,
                "output_text": item.output_text,
                "is_error": item.is_error,
            }

        # Default: reasoning / thinking items
        return {
            "kind": "reasoning",
            "text": item.text,
            "summary": item.summary,
            "raw_item": item.raw_item,
            "replay_hint": item.replay_hint,
        }
