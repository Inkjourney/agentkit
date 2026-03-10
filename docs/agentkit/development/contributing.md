# Contributing

## Development Setup

```bash
uv sync
```

## Run Tests

```bash
uv run pytest tests
```

When changing one area, run the narrowest relevant slice first. Examples:

```bash
uv run pytest tests/test_openai_provider.py
uv run pytest tests/test_fs_tools.py
```

## Build Documentation

```bash
uv run mkdocs build --strict
```

## Coding Guidelines

- Keep public APIs stable or document breaking changes.
- Add tests for behavior changes (providers, tools, lifecycle, config validation).
- Keep provider adapters aligned to `UnifiedLLMRequest` / `UnifiedLLMResponse` contracts.
- Preserve canonical run-event semantics when changing reporting or logging.

## Documentation Guidelines

- Document only public interfaces.
- Prefer runnable examples over pseudocode.
- Keep provider-specific behavior in concept/guide pages and normalized behavior in API pages.
- When behavior is only recoverable from implementation, say `Behavior inferred from code inspection.`

## Pull Request Checklist

- Tests pass locally
- Docs updated for API/behavior changes
- Config/CLI changes include examples
- Trace/observability impact documented when relevant
