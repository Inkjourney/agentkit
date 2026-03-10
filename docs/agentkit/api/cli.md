# CLI API

## Overview

The CLI surface currently lives in `agentkit.cli.main` and powers the
`llm-agent` entry point declared in `packages/agentkit/pyproject.toml`.

## Key Functions

- `build_parser`
- `main`

## API Reference

::: agentkit.cli

::: agentkit.cli.main

## Notes

The public CLI surface currently contains one subcommand, `run`, with these flags:

- `--task`
- `--task-file`
- `--report-json`
