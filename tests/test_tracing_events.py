from __future__ import annotations

from datetime import datetime

from agentkit.runlog.events import RUN_EVENT_SCHEMA, RunEvent


def test_run_event_to_dict_has_expected_shape() -> None:
    event = RunEvent.create(
        seq=2,
        run_id="rid-1",
        kind="model_responded",
        step=1,
        payload={"input_items": 3},
    )
    payload = event.to_dict()

    datetime.fromisoformat(event.ts)
    assert payload["schema"] == RUN_EVENT_SCHEMA
    assert payload["seq"] == 2
    assert payload["run_id"] == "rid-1"
    assert payload["kind"] == "model_responded"
    assert payload["step"] == 1
    assert payload["payload"] == {"input_items": 3}
