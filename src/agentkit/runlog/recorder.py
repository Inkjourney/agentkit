"""Run-scoped canonical event recorder."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from agentkit.runlog.events import RunEvent, RunEventKind
from agentkit.runlog.sinks import RunEventSink


class RunRecorder:
    """Emit canonical run events to one or more sinks."""

    def __init__(
        self,
        sinks: Sequence[RunEventSink],
        *,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        """Create a recorder that multicasts canonical events to configured sinks."""
        self._sinks = list(sinks)
        self._run_id_factory = run_id_factory or _build_run_id
        self._current_run_id: str | None = None
        self._seq = 0

    @property
    def current_run_id(self) -> str | None:
        """Return the active run id, or ``None`` when no run is open."""
        return self._current_run_id

    def start_run(
        self,
        *,
        task: str = "",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Open a new run and emit the initial ``run_started`` event."""
        if self._current_run_id is not None:
            raise RuntimeError("A run is already active.")

        run_id = self._run_id_factory()
        self._current_run_id = run_id
        self._seq = 0

        self.emit(
            "run_started",
            payload={
                "task": task,
                "context": dict(context or {}),
            },
        )
        return run_id

    def emit(
        self,
        kind: RunEventKind,
        *,
        step: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        """Emit one run event to every sink and return the created event."""
        if self._current_run_id is None:
            raise RuntimeError("No active run. Call start_run first.")
        self._seq += 1
        event = RunEvent.create(
            seq=self._seq,
            run_id=self._current_run_id,
            kind=kind,
            step=step,
            payload=payload,
        )
        for sink in self._sinks:
            sink.consume(event)
        return event

    def end_run(self, *, status: str, payload: dict[str, Any] | None = None) -> None:
        """Emit the terminal event for the current run and clear recorder state."""
        run_payload = dict(payload or {})
        run_payload["status"] = status
        self.emit(
            "run_finished",
            payload=run_payload,
        )
        self._current_run_id = None


def _build_run_id() -> str:
    """Build a run id from UTC timestamp and random suffix."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"
