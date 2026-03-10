# Repository Guidelines

## Overview

- `agentkit` is a Python 3.12+ library and CLI for tool-using LLM agents.
- Main entry points:
  - Python SDK: `src/agentkit/__init__.py` exposes `create_agent`, `Agent`, and `load_config`.
  - CLI: `uv run agentkit --config <file> run --task "..."`.
- Runtime flow: config load -> workspace init -> provider build -> tool registry/load -> agent loop -> runlog/report.
- Keep language consistent with the surrounding file:
  - `README.md` is English and links to `docs/README.zh-CN.md`.
  - `docs/README.zh-CN.md` is Chinese.
  - `docs/agentkit/**`, code, tests, and docstrings are English.

## Project Layout

- `src/agentkit/config/`: dataclass schemas, config loader, provider defaults.
- `src/agentkit/workspace/`: workspace layout and the `WorkspaceFS` isolation boundary.
- `src/agentkit/llm/`: provider-agnostic request/response types, usage helpers, provider factory, provider adapters.
- `src/agentkit/tools/`: tool base classes, registry, loader, and built-in tool library.
- `src/agentkit/agent/`: agent loop, budgets, reports, tool runtime.
- `src/agentkit/runlog/`: canonical run events, recorder, JSONL sink.
- `src/agentkit/cli/`: argparse CLI entrypoint.
- `tests/`: unit tests grouped by subsystem.
- `docs/agentkit/`: MkDocs documentation.
- `examples/`: sample config files.

## Core Invariants

- Preserve workspace isolation. Code that operates on agent-visible files should go through `WorkspaceFS`, not direct `Path` access.
- Keep provider adapters thin. Provider modules should translate between external API payloads and `UnifiedLLMRequest` / `UnifiedLLMResponse`, not introduce agent-loop policy.
- Preserve the normalized LLM contract in `src/agentkit/llm/types.py`: status mapping, tool-call structure, usage accounting, and conversation-state updates must stay consistent across providers.
- `Agent.from_config()` always loads the built-in tool library, but only tools in `config.tools.allowed` are exposed to the model. Do not blur registry loading with allowlisting.
- Runlog semantics are part of the contract. `run_started`, `model_responded`, `tool_executed`, and `run_finished` ordering and payload meaning are heavily tested.
- Keep tool names stable and dot-free. `ToolRegistry` rejects names containing `.` and relies on stable error codes/messages for model-facing failures.
- Tool argument validation only supports a focused JSON Schema subset. If you expand it, update tests and docs deliberately.

## Working Conventions

- Use `uv` for environment and command execution.
- Prefer small, focused edits in the subsystem you are changing; this repo is intentionally modular.
- Maintain the existing style:
  - `from __future__ import annotations`
  - typed functions and dataclasses
  - concise but meaningful docstrings on public functions/classes
- Keep public APIs stable unless the task explicitly requires a breaking change.
- When behavior changes, update both tests and docs in the same change.
- Avoid live network calls in tests; provider tests in this repo use fakes/monkeypatching.

## Subsystem Notes

### Config

- Put config validation in schema `__post_init__` methods or `config/provider_defaults.py`, not scattered in callers.
- When adding provider-specific config, update all of:
  - `src/agentkit/config/schema.py`
  - `src/agentkit/config/provider_defaults.py`
  - `src/agentkit/config/loader.py` if load behavior changes
  - relevant tests and docs

### Workspace

- `WorkspaceFS.resolve_path()` is the trust boundary for path containment.
- If you add workspace-facing functionality, include escape-path tests and missing-path tests.

### Providers / LLM

- If you add or change a provider, update:
  - `ProviderKind` in `src/agentkit/config/schema.py`
  - defaults/env handling in `src/agentkit/config/provider_defaults.py`
  - factory wiring in `src/agentkit/llm/factory.py`
  - provider-specific tests
  - docs under `docs/agentkit/concepts/` and `docs/agentkit/guides/`
- Preserve usage normalization and reasoning/tool-call parsing behavior; tests assert these details.

### Tools

- Built-in tools live under `src/agentkit/tools/library/`.
- Auto-loading expects modules to expose `build_tools(fs)`, `build_tools()`, or `TOOLS`.
- Keep tool-specific success/error formatting inside the tool module via formatter hooks or `ToolModelError`, not in `ToolRegistry`.
- When adding a built-in tool, update:
  - the library module
  - `src/agentkit/tools/library/fs_tools.py` if it belongs in the default FS bundle
  - tests for loader/registry/runtime behavior
  - custom-tools or tools-system docs if user-visible

### Agent Loop / Runlog / CLI

- Changes to `src/agentkit/agent/agent.py`, runlog projection, or CLI flags usually require synchronized test updates.
- If CLI behavior changes, update `tests/test_cli_main.py` and `docs/agentkit/guides/cli-usage.md`.
- If run report or runlog payloads change, update tests before touching docs so contract changes stay explicit.

## Verification

- Setup: `uv sync`
- Run the narrowest relevant tests first:
  - `uv run pytest tests/test_config_loader.py`
  - `uv run pytest tests/test_fs_tools.py`
  - `uv run pytest tests/test_agent_run.py`
  - `uv run pytest tests/test_openai_provider.py`
  - `uv run pytest tests/test_cli_main.py`
- Full test suite: `uv run pytest tests`
- Lint: `uv run ruff check src tests`
- Docs build when docs or public APIs change: `uv run mkdocs build --strict`

## Documentation Expectations

- Document public behavior, not private implementation trivia.
- Prefer runnable examples over pseudocode.
- Keep provider-specific details in concept/guide pages and normalized contracts in API pages.
- If a behavior is only known from implementation, state `Behavior inferred from code inspection.`

## Common Pitfalls

- Forgetting that `tools.allowed` defaults to an empty list.
- Bypassing `WorkspaceFS` in tool or agent code.
- Changing provider parsing without updating usage/state/tool-call tests.
- Changing run-event payloads or schema meaning without updating runlog/report tests.
- Editing docs/examples for config or CLI behavior in one place but not the others.
