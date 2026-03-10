"""Runtime budget guards."""

from __future__ import annotations

import time

from agentkit.errors import BudgetExceededError


class RuntimeBudget:
    """Track and enforce runtime limits for a single agent run."""

    def __init__(self, *, max_steps: int, time_budget_s: int) -> None:
        """Initialize budget thresholds and start timing.

        Args:
            max_steps: Maximum number of model/tool loop iterations allowed.
            time_budget_s: Maximum wall-clock runtime in seconds.

        Returns:
            None
        """
        self.max_steps = max_steps
        self.time_budget_s = time_budget_s
        self.started_monotonic = time.monotonic()

    def ensure_can_continue(self, step_index: int) -> None:
        """Raise if the run exceeded configured step or time budgets.

        Args:
            step_index: Zero-based index of the next step to execute.

        Returns:
            None

        Raises:
            agentkit.errors.BudgetExceededError: If the step count or elapsed time is
                above configured limits.
        """
        if step_index >= self.max_steps:
            raise BudgetExceededError(
                f"Step budget exceeded: step={step_index}, max_steps={self.max_steps}"
            )
        elapsed = time.monotonic() - self.started_monotonic
        if elapsed > self.time_budget_s:
            raise BudgetExceededError(
                f"Time budget exceeded: elapsed={elapsed:.1f}s, budget={self.time_budget_s}s"
            )
