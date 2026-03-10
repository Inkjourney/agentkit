# Run Log API

## Overview

The `runlog` package defines canonical run events and writes structured JSONL run
logs.

## Key Classes

- `RunEvent`
- `RunEventSink`
- `RunRecorder`
- `JsonlRunLogSink`

## API Reference

::: agentkit.runlog

::: agentkit.runlog.events

::: agentkit.runlog.recorder

::: agentkit.runlog.jsonl

::: agentkit.runlog.sinks

## Notes

When redaction is enabled, key-name heuristics redact sensitive fields and truncate
long strings.

For tool events, the run log records both:

- `output`: the raw tool result kept by the runtime
- `model_payload`: the exact tool result payload sent back into model history
