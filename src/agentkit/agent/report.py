"""Run report projection from canonical run events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agentkit.llm.types import Usage
from agentkit.llm.usage import usage_from_payload
from agentkit.runlog.events import RunEvent
from agentkit.runlog.sinks import RunEventSink


@dataclass(slots=True)
class RunStep:
    """One model turn summary in the returned run report."""

    step: int
    assistant_text: str
    tool_calls: list[str] = field(default_factory=list)
    ts: str = ""


@dataclass(slots=True)
class RunToolCall:
    """One tool execution record in the returned run report."""

    step: int
    call_id: str
    name: str
    arguments: dict[str, Any]
    is_error: bool
    output: Any = None
    error: str | None = None
    model_payload: Any = None
    duration_ms: float | None = None
    ts: str = ""


@dataclass(slots=True)
class RunReport:
    """Structured result object returned by :meth:`agentkit.agent.Agent.run`."""

    task: str
    started_at: str
    run_id: str
    runlog_path: str | None = None
    status: str = "failed"
    completed: bool = False
    final_output: str = ""
    reason: str | None = None
    finished_at: str | None = None
    usage: Usage = field(default_factory=Usage)
    steps: list[RunStep] = field(default_factory=list)
    tool_calls: list[RunToolCall] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the report into plain data for CLI or API serialization."""
        return asdict(self)


class RunReportProjector(RunEventSink):
    """Project canonical run events into a :class:`RunReport`."""

    def __init__(self) -> None:
        """Initialize empty projection state for a single run."""
        self._task = ""
        self._started_at = ""
        self._run_id = ""
        self._status = "failed"
        self._completed = False
        self._final_output = ""
        self._reason: str | None = None
        self._finished_at: str | None = None
        self._usage = Usage()
        self._steps: list[RunStep] = []
        self._tool_calls: list[RunToolCall] = []

    def consume(self, event: RunEvent) -> None:
        """Update the projection incrementally from one canonical run event."""
        if event.kind == "run_started":
            self._task = str(event.payload.get("task", ""))
            self._started_at = event.ts
            self._run_id = event.run_id
            return

        if event.kind == "model_responded":
            tool_call_names: list[str] = []
            requested_tools = event.payload.get("requested_tools", [])
            if isinstance(requested_tools, list):
                for item in requested_tools:
                    if isinstance(item, dict) and item.get("name") is not None:
                        tool_call_names.append(str(item["name"]))
            self._steps.append(
                RunStep(
                    step=event.step or 0,
                    assistant_text=str(event.payload.get("output_text", "")),
                    tool_calls=list(tool_call_names)
                    if isinstance(tool_call_names, list)
                    else [],
                    ts=event.ts,
                )
            )
            return

        if event.kind == "tool_executed":
            arguments = event.payload.get("arguments")
            self._tool_calls.append(
                RunToolCall(
                    step=event.step or 0,
                    call_id=str(event.payload.get("call_id", "")),
                    name=str(event.payload.get("name", "")),
                    arguments=dict(arguments) if isinstance(arguments, dict) else {},
                    is_error=bool(event.payload.get("is_error", False)),
                    output=event.payload.get("output"),
                    error=event.payload.get("error"),
                    model_payload=event.payload.get("model_payload"),
                    duration_ms=event.payload.get("duration_ms"),
                    ts=event.ts,
                )
            )
            return

        if event.kind == "run_finished":
            self._finished_at = event.ts
            self._status = str(event.payload.get("status", self._status))
            self._completed = self._status == "completed"
            if "final_output" in event.payload:
                self._final_output = str(event.payload.get("final_output", ""))
            reason = event.payload.get("reason")
            if reason is not None:
                self._reason = str(reason)
            usage = event.payload.get("usage")
            if isinstance(usage, dict):
                self._usage = usage_from_payload(usage)

    def build(self, *, runlog_path: str | None = None) -> RunReport:
        """Materialize the current projection into an immutable report object."""
        if not self._run_id or not self._started_at:
            raise RuntimeError("RunReportProjector has not received run_started.")

        return RunReport(
            task=self._task,
            started_at=self._started_at,
            run_id=self._run_id,
            runlog_path=runlog_path,
            status=self._status,
            completed=self._completed,
            final_output=self._final_output,
            reason=self._reason,
            finished_at=self._finished_at,
            usage=self._usage,
            steps=list(self._steps),
            tool_calls=list(self._tool_calls),
        )

    @property
    def step_count(self) -> int:
        """Return the number of model turns observed so far."""
        return len(self._steps)

    @property
    def tool_call_count(self) -> int:
        """Return the number of tool executions observed so far."""
        return len(self._tool_calls)
