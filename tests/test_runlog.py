from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agentkit.agent.report import RunReportProjector
from agentkit.runlog.events import RUN_EVENT_SCHEMA, RunEvent
from agentkit.runlog.recorder import RunRecorder


@dataclass(slots=True)
class InMemorySink:
    events: list[RunEvent] = field(default_factory=list)

    def consume(self, event: RunEvent) -> None:
        self.events.append(event)


def test_run_recorder_emits_schema_and_monotonic_seq() -> None:
    sink = InMemorySink()
    recorder = RunRecorder([sink], run_id_factory=lambda: "rid-1")

    run_id = recorder.start_run(task="demo", context={"model": "demo-model"})
    recorder.emit(
        "model_responded",
        step=0,
        payload={"status": "completed", "output_text": "ok", "requested_tools": []},
    )
    recorder.end_run(status="completed", payload={"step_count": 1})

    assert run_id == "rid-1"
    assert [event.seq for event in sink.events] == [1, 2, 3]
    assert all(event.schema == RUN_EVENT_SCHEMA for event in sink.events)
    assert all(event.run_id == "rid-1" for event in sink.events)
    assert sink.events[0].payload["context"] == {"model": "demo-model"}
    for event in sink.events:
        datetime.fromisoformat(event.ts)


def test_run_report_projector_projects_success_flow() -> None:
    projector = RunReportProjector()
    recorder = RunRecorder([projector], run_id_factory=lambda: "rid-success")

    recorder.start_run(task="say hello")
    recorder.emit(
        "model_responded",
        step=0,
        payload={
            "status": "requires_tool",
            "reason": "tool_call",
            "output_text": "calling tool",
            "requested_tools": [
                {
                    "kind": "tool_call",
                    "call_id": "call-1",
                    "name": "echo",
                    "arguments": {"text": "hello"},
                    "raw_arguments": '{"text":"hello"}',
                }
            ],
        },
    )
    recorder.emit(
        "tool_executed",
        step=0,
        payload={
            "call_id": "call-1",
            "name": "echo",
            "is_error": False,
            "arguments": {"text": "hello"},
            "output": {"echo": "hello"},
            "model_payload": "The file draft.txt has been edited.",
            "duration_ms": 1.2,
        },
    )
    recorder.emit(
        "model_responded",
        step=1,
        payload={
            "status": "completed",
            "reason": "stop",
            "output_text": "done",
            "requested_tools": [],
        },
    )
    recorder.end_run(
        status="completed",
        payload={
            "reason": "stop",
            "step_count": 2,
            "tool_call_count": 1,
            "final_output": "done",
            "usage": {
                "input_tokens": 12,
                "output_tokens": 5,
                "total_tokens": 17,
                "reasoning_tokens": 3,
                "cache_read_tokens": 2,
                "cache_write_tokens": 1,
            },
        },
    )

    report = projector.build(runlog_path="logs/run_rid-success.jsonl")
    assert report.run_id == "rid-success"
    assert report.runlog_path == "logs/run_rid-success.jsonl"
    assert report.status == "completed"
    assert report.completed is True
    assert report.final_output == "done"
    assert report.usage.total_tokens == 17
    assert report.usage.reasoning_tokens == 3
    assert len(report.steps) == 2
    assert len(report.tool_calls) == 1
    assert report.tool_calls[0].call_id == "call-1"
    assert report.tool_calls[0].model_payload == "The file draft.txt has been edited."


def test_run_report_projector_projects_failed_flow() -> None:
    projector = RunReportProjector()
    recorder = RunRecorder([projector], run_id_factory=lambda: "rid-failed")

    recorder.start_run(task="boom")
    recorder.end_run(
        status="failed",
        payload={
            "step_count": 0,
            "tool_call_count": 0,
            "error_type": "RuntimeError",
            "error_message": "boom",
        },
    )

    report = projector.build()
    assert report.run_id == "rid-failed"
    assert report.status == "failed"
    assert report.completed is False
    assert report.final_output == ""
