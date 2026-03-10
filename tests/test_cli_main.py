from __future__ import annotations

import importlib
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from agentkit.errors import AgentFrameworkError

cli_main = importlib.import_module("agentkit.cli.main")


def test_load_task_prefers_inline_task(tmp_path: Path) -> None:
    file_path = tmp_path / "task.txt"
    file_path.write_text("from-file", encoding="utf-8")

    assert cli_main._load_task("inline", str(file_path)) == "inline"
    assert cli_main._load_task(None, str(file_path)) == "from-file"


def test_load_task_requires_input() -> None:
    with pytest.raises(SystemExit, match="Please provide --task or --task-file"):
        cli_main._load_task(None, None)


def test_run_command_success_writes_report_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class DummyReport:
        final_output = "done"

        @staticmethod
        def to_dict() -> dict[str, Any]:
            return {"final_output": "done", "completed": True}

    class DummyAgent:
        def run(self, task: str) -> DummyReport:
            assert task == "ship it"
            return DummyReport()

    monkeypatch.setattr(cli_main, "load_config", lambda _path: object())
    monkeypatch.setattr(cli_main.Agent, "from_config", staticmethod(lambda _cfg: DummyAgent()))

    report_json = tmp_path / "report.json"
    args = Namespace(
        task="ship it",
        task_file=None,
        config="config.yaml",
        report_json=str(report_json),
    )
    cli_main._run_command(args)

    assert json.loads(report_json.read_text(encoding="utf-8")) == {
        "final_output": "done",
        "completed": True,
    }
    assert capsys.readouterr().out.strip() == "done"


def test_run_command_translates_framework_error_to_exit_code_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class DummyAgent:
        def run(self, _task: str) -> None:
            raise AgentFrameworkError("runtime failure")

    monkeypatch.setattr(cli_main, "load_config", lambda _path: object())
    monkeypatch.setattr(cli_main.Agent, "from_config", staticmethod(lambda _cfg: DummyAgent()))

    args = Namespace(task="run", task_file=None, config="config.yaml", report_json=None)
    with pytest.raises(SystemExit) as exc_info:
        cli_main._run_command(args)

    assert exc_info.value.code == 2
    assert "[agent-error] runtime failure" in capsys.readouterr().err


def test_main_dispatches_run_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class DummyParser:
        def parse_args(self) -> Namespace:
            return Namespace(
                command="run",
                task="run now",
                task_file=None,
                config="config.yaml",
                report_json=None,
            )

    monkeypatch.setattr(cli_main, "build_parser", lambda: DummyParser())
    monkeypatch.setattr(cli_main, "_run_command", lambda args: captured.setdefault("args", args))

    cli_main.main()

    assert captured["args"].command == "run"
