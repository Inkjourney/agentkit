"""Run event schema shared by reporting and run log projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RUN_EVENT_SCHEMA = "agentkit.run_event.v3"

RunEventKind = Literal[
    "run_started",
    "model_responded",
    "tool_executed",
    "run_finished",
]


def _utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RunEvent:
    """Canonical runtime event emitted by :class:`agentkit.runlog.RunRecorder`."""

    schema: str
    seq: int
    ts: str
    run_id: str
    kind: RunEventKind
    step: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        seq: int,
        run_id: str,
        kind: RunEventKind,
        step: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "RunEvent":
        """Create a run event with the canonical schema version and timestamp."""
        return cls(
            schema=RUN_EVENT_SCHEMA,
            seq=seq,
            ts=_utc_now(),
            run_id=run_id,
            kind=kind,
            step=step,
            payload=payload or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event for sinks that need plain dictionaries."""
        return {
            "schema": self.schema,
            "seq": self.seq,
            "ts": self.ts,
            "run_id": self.run_id,
            "kind": self.kind,
            "step": self.step,
            "payload": self.payload,
        }
