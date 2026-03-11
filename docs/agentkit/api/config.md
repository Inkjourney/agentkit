# Config API

## Overview

The config package loads YAML or JSON, validates runtime configuration dataclasses,
and applies provider-specific defaults.

## Key Classes

- `AgentkitConfig`
- `ProviderConfig`
- `AgentConfig`
- `BudgetConfig`
- `ToolConfig`
- `RunLogConfig`
- `WorkspaceConfig`
- `ProviderDefaults`

## API Reference

::: agentkit.config

::: agentkit.config.schema

::: agentkit.config.loader

::: agentkit.config.provider_defaults

## Notes

`load_config(...)` enforces provider API key presence with provider-specific
defaults.

`agent.budget.max_input_chars` is a public config field, but the current runtime
does not consume it yet. `tools.entries` is consumed by `Agent.from_config` and
loads custom tool files/directories in addition to the built-in tool library.
