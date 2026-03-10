# Errors API

## Overview

The `errors` module defines framework-specific exceptions and structured provider
issue metadata.

## Key Classes

- `AgentFrameworkError`
- `ConfigError`
- `WorkspaceError`
- `ToolError`
- `ProviderError`
- `BudgetExceededError`
- `ProviderIssue`

## API Reference

::: agentkit.errors

## Notes

`ProviderError` may include a `ProviderIssue` object with category, status code,
retryability, and raw provider payload.
