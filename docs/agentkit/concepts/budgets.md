# Budgets

## Overview

Runtime budgets limit a single `Agent.run` execution by:

- maximum loop steps (`max_steps`)
- maximum wall-clock time (`time_budget_s`)

## Why It Exists

Budgets prevent runaway loops and make execution limits explicit in configuration.

## Architecture

```mermaid
graph TD
    C[BudgetConfig] --> R[RuntimeBudget]
    R --> E[ensure_can_continue(step)]
    E --> S{step >= max_steps?}
    S -- yes --> X[raise BudgetExceededError]
    S -- no --> T{elapsed > time_budget_s?}
    T -- yes --> X
    T -- no --> OK[continue run loop]
```

## Key Classes

| Class | Description |
| ----- | ----------- |
| `agentkit.config.BudgetConfig` | Config model for step/time/input-size limits. |
| `agentkit.agent.RuntimeBudget` | Runtime guard invoked each loop iteration. |
| `agentkit.errors.BudgetExceededError` | Raised when step/time limit is exceeded. |

## How It Works

1. `Agent.run` constructs `RuntimeBudget` from config values.
2. Before each model call, `ensure_can_continue(step)` checks thresholds.
3. Exceeded limits raise `BudgetExceededError`, which terminates the run.

## Current Enforcement

| Field | Stored in config | Enforced by runtime |
| --- | --- | --- |
| `max_steps` | Yes | Yes |
| `time_budget_s` | Yes | Yes |
| `max_input_chars` | Yes | No |

!!! note
    Behavior inferred from code inspection: `BudgetConfig.max_input_chars` is
    validated but not consumed by `Agent.run`.

## Example

```python
from agentkit.agent.budgets import RuntimeBudget
from agentkit.errors import BudgetExceededError

budget = RuntimeBudget(max_steps=2, time_budget_s=60)
budget.ensure_can_continue(0)

try:
    budget.ensure_can_continue(2)
except BudgetExceededError as exc:
    print(str(exc))
```

## Related Concepts

- [Agent Lifecycle](./agent-lifecycle.md)
- [Configuration](../getting-started/configuration.md)
