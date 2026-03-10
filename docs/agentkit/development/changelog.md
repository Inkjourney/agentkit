# Changelog

## Unreleased

### Changed

- Canonical runtime facts are emitted through `agentkit.runlog` as `RunEvent` records.
- `Agent.run` returns `RunReport`, projected from the canonical event stream.
- Run logs are written by `JsonlRunLogSink` to `workspace/logs/run_<run_id>.jsonl`.
- Provider defaults are centralized in `agentkit.config.provider_defaults`.
- OpenAI-compatible Qwen and vLLM adapters add provider-specific thinking controls.

### Breaking Changes

- Removed `SessionState`, `StepRecord`, and `ToolCallRecord` from public runtime contracts.
- Removed the `tracing` package and merged JSONL sink responsibilities into `agentkit.runlog`.
- Run-event JSONL uses the `agentkit.run_event.v3` envelope.
- Built-in filesystem tools now expose `view`, `create_file`, `str_replace`, and `word_count`; the old `fs_*` tool names were removed.
- CLI output persistence flag is `--report-json` rather than `--session-json`.

## 0.1.0

Initial AgentKit release in this repository.

### Added

- Unified agent runtime loop (`Agent`) with tool-call continuation
- Configuration schema + loader with YAML/JSON and environment expansion
- Provider adapters:
  - OpenAI (`responses`, `chat_completions`)
  - Anthropic (`messages`)
  - Gemini (`generateContent`)
  - Qwen (OpenAI-compatible)
  - vLLM (OpenAI-compatible)
- Tool abstractions (`Tool`, `FunctionTool`) and registry/loader system
- Built-in filesystem tools (`view`, `create_file`, `str_replace`, `word_count`)
- Workspace-isolated filesystem facade (`WorkspaceFS`)
- Structured JSONL run logging and canonical run events
- CLI entrypoint (`agentkit`)
