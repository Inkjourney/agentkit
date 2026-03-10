# Installation

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (recommended for this workspace)

## Install In This Repository

From the repository root:

```bash
uv sync
```

This installs the workspace packages, including `agentkit`, and exposes the
`llm-agent` CLI entry point defined in `packages/agentkit/pyproject.toml`.

## Verify Installation

```bash
uv run llm-agent --help
```

If the command succeeds, the package import path and CLI entry point are both
available.

!!! tip
    AgentKit is developed as the workspace package at `packages/agentkit`.

## Run Tests

```bash
uv run pytest packages/agentkit/tests
```

## Build The Docs

```bash
uv run mkdocs build --strict
```

## Related

- [Quickstart](./quickstart.md)
- [Configuration](./configuration.md)
