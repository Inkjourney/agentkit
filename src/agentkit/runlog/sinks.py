"""Sink protocol for run event consumers."""

from __future__ import annotations

from typing import Protocol

from agentkit.runlog.events import RunEvent


class RunEventSink(Protocol):
    """Consume one canonical runtime event."""

    def consume(self, event: RunEvent) -> None:
        """Handle one event emitted by :class:`agentkit.runlog.recorder.RunRecorder`."""
        ...
