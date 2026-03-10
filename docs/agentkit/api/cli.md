# CLI API

## Overview

The CLI surface currently lives in `agentkit.cli.main` and powers the
`agentkit` entry point declared in the repository root `pyproject.toml`.

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
