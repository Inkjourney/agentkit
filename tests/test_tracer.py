from __future__ import annotations

import json
from pathlib import Path

from agentkit.config.schema import RunLogConfig
from agentkit.runlog import JsonlRunLogSink
from agentkit.runlog.recorder import RunRecorder
from agentkit.workspace.fs import WorkspaceFS


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_jsonl_runlog_sink_emits_run_lifecycle_and_sanitized_payload(
    workspace_fs: WorkspaceFS,
) -> None:
    sink = JsonlRunLogSink(
        workspace_fs,
        RunLogConfig(enabled=True, redact=True, max_text_chars=20),
    )
    recorder = RunRecorder([sink], run_id_factory=lambda: "20260218T000000_deadbeef")

    run_id = recorder.start_run(task="do work", context={"model": "demo-model"})
    runlog_path = sink.runlog_path_for_run(run_id)
    recorder.emit(
        "model_responded",
        step=0,
        payload={
            "status": "completed",
            "output_text": "x" * 30,
            "requested_tools": [],
            "api_key": "secret-key",
            "nested": {"password": "pw", "note": "abcdefghijklmno" * 2},
            "list": [{"authorization": "token"}],
        },
    )
    recorder.emit(
        "tool_executed",
        step=0,
        payload={
            "call_id": "call-1",
            "name": "str_replace",
            "is_error": False,
            "arguments": {"path": "draft.txt"},
            "output": {"path": "draft.txt", "replacements": 1},
            "model_payload": "The file draft.txt has been edited. " + ("y" * 30),
            "duration_ms": 2.5,
        },
    )
    recorder.end_run(status="completed", payload={"step_count": 1})

    assert run_id == "20260218T000000_deadbeef"
    assert runlog_path.name == "run_20260218T000000_deadbeef.jsonl"
    assert sink.current_run_id is None

    rows = _read_jsonl(runlog_path)
    assert rows[0]["kind"] == "run_started"
    assert rows[0]["payload"]["context"]["model"] == "demo-model"
    assert rows[1]["kind"] == "model_responded"
    assert rows[1]["payload"]["api_key"] == "***REDACTED***"
    assert rows[1]["payload"]["nested"]["password"] == "***REDACTED***"
    assert rows[1]["payload"]["nested"]["note"] == "abcdefghijklmnoabcde...<truncated>"
    assert rows[1]["payload"]["list"][0]["authorization"] == "***REDACTED***"
    assert rows[1]["payload"]["output_text"] == "xxxxxxxxxxxxxxxxxxxx...<truncated>"
    assert rows[2]["kind"] == "tool_executed"
    assert rows[2]["payload"]["model_payload"].startswith("The file draft.txt h")
    assert rows[2]["payload"]["model_payload"].endswith("...<truncated>")
    assert rows[3]["kind"] == "run_finished"
    assert rows[3]["payload"]["status"] == "completed"


def test_jsonl_runlog_sink_redacts_common_secret_like_keys(
    workspace_fs: WorkspaceFS,
) -> None:
    sink = JsonlRunLogSink(
        workspace_fs,
        RunLogConfig(enabled=True, redact=True, max_text_chars=100),
    )
    recorder = RunRecorder([sink], run_id_factory=lambda: "20260218T000000_secretkeys")

    run_id = recorder.start_run(task="redact", context={"model": "demo-model"})
    runlog_path = sink.runlog_path_for_run(run_id)
    recorder.emit(
        "model_responded",
        step=0,
        payload={
            "status": "completed",
            "output_text": "ok",
            "requested_tools": [],
            "secret_value": "s3cr3t",
            "access_token": "token-123",
            "nested": {
                "authorization": "Bearer abc",
                "db_password": "pw-123",
            },
        },
    )
    recorder.end_run(status="completed", payload={"step_count": 1})

    rows = _read_jsonl(runlog_path)
    payload = rows[1]["payload"]
    assert payload["secret_value"] == "***REDACTED***"
    assert payload["access_token"] == "***REDACTED***"
    assert payload["nested"]["authorization"] == "***REDACTED***"
    assert payload["nested"]["db_password"] == "***REDACTED***"


def test_jsonl_runlog_sink_disabled_does_not_write_files(
    workspace_fs: WorkspaceFS,
) -> None:
    sink = JsonlRunLogSink(
        workspace_fs,
        RunLogConfig(enabled=False, redact=True, max_text_chars=5),
    )
    recorder = RunRecorder([sink], run_id_factory=lambda: "20260218T000000_disabled")

    run_id = recorder.start_run(task="disabled", context={"model": "disabled-model"})
    runlog_path = sink.runlog_path_for_run(run_id)
    recorder.emit(
        "model_responded",
        step=0,
        payload={
            "status": "completed",
            "output_text": "",
            "requested_tools": [],
            "api_key": "secret",
        },
    )
    recorder.end_run(status="completed")

    assert run_id == "20260218T000000_disabled"
    assert sink.current_run_id is None
    assert runlog_path.exists() is False
