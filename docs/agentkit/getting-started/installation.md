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
`agentkit` CLI entry point defined in the repository root `pyproject.toml`.

## Verify Installation

```bash
uv run agentkit --help
```

If the command succeeds, the package import path and CLI entry point are both
available.

!!! tip
    The package source lives in `src/agentkit`, and the test suite lives in
    `tests`.

## Run Tests

```bash
uv run pytest tests
```

## Build The Docs

```bash
uv run mkdocs build --strict
```

## Related

- [Quickstart](./quickstart.md)
- [Configuration](./configuration.md)
