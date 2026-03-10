"""JSONL run log sink with basic redaction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentkit.config.schema import RunLogConfig
from agentkit.constants import DEFAULT_RUNLOG_PATH, SENSITIVE_KEYS
from agentkit.runlog.events import RunEvent
from agentkit.workspace.fs import WorkspaceFS


class JsonlRunLogSink:
    """Write canonical run events to JSONL with optional redaction."""

    def __init__(self, fs: WorkspaceFS, config: RunLogConfig) -> None:
        """Prepare the sink and ensure the run-log directory exists."""
        self._enabled = config.enabled
        self._redact = config.redact
        self._max_text_chars = config.max_text_chars
        self._default_path: Path = fs.resolve_path(DEFAULT_RUNLOG_PATH)
        self._default_path.parent.mkdir(parents=True, exist_ok=True)
        self._current_path: Path | None = None
        self._current_run_id: str | None = None

    @property
    def enabled(self) -> bool:
        """Return whether this sink should persist events to disk."""
        return self._enabled

    @property
    def current_run_id(self) -> str | None:
        """Return the run id currently being written, if any."""
        return self._current_run_id

    @property
    def current_runlog_path(self) -> Path:
        """Return the active run-log path, or the default path before a run starts."""
        return self._current_path or self._default_path

    def runlog_path_for_run(self, run_id: str) -> Path:
        """Return the per-run JSONL path for a given run id."""
        return self._default_path.parent / f"run_{run_id}.jsonl"

    def consume(self, event: RunEvent) -> None:
        """Persist one event, applying redaction and truncation when enabled."""
        if event.kind == "run_started":
            self._current_run_id = event.run_id
            self._current_path = self.runlog_path_for_run(event.run_id)

        if not self._enabled:
            if event.kind == "run_finished":
                self._current_run_id = None
                self._current_path = None
            return

        payload: dict[str, Any] = event.to_dict()
        if self._redact:
            # Redact before truncation so secrets are never partially preserved in
            # the run log, even when a long string would be shortened.
            payload = self._sanitize(payload)

        target_path = self._current_path or self.runlog_path_for_run(event.run_id)
        with target_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        if event.kind == "run_finished":
            self._current_run_id = None
            self._current_path = None

    def _sanitize(self, obj: Any, *, key_hint: str = "") -> Any:
        """Recursively redact sensitive keys and cap very large text fields."""
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for key, value in obj.items():
                lowered = key.lower()
                if any(token in lowered for token in SENSITIVE_KEYS):
                    out[key] = "***REDACTED***"
                else:
                    out[key] = self._sanitize(value, key_hint=key)
            return out
        if isinstance(obj, list):
            return [self._sanitize(item, key_hint=key_hint) for item in obj]
        if isinstance(obj, str):
            if len(obj) > self._max_text_chars:
                return obj[: self._max_text_chars] + "...<truncated>"
            return obj
        return obj
