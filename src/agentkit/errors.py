"""Custom framework exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class AgentFrameworkError(Exception):
    """Base class for all framework-specific exceptions."""


class ConfigError(AgentFrameworkError):
    """Raised when configuration loading or validation fails."""


class WorkspaceError(AgentFrameworkError):
    """Raised for workspace path isolation and filesystem operation errors."""


class ToolError(AgentFrameworkError):
    """Raised for tool registration, validation, or execution failures."""


ProviderIssueCategory = Literal[
    "auth",
    "rate_limit",
    "invalid_request",
    "timeout",
    "upstream",
    "safety",
    "parse",
    "unknown",
]


@dataclass(slots=True)
class ProviderIssue:
    """Structured provider failure metadata for logging and retry decisions."""

    category: ProviderIssueCategory
    http_status: int | None = None
    provider_code: str | None = None
    retryable: bool = False
    raw: dict[str, Any] | None = None


class ProviderError(AgentFrameworkError):
    """Raised for model provider request failures or invalid responses."""

    def __init__(self, message: str, *, issue: ProviderIssue | None = None) -> None:
        """Attach optional structured provider metadata to the raised error."""
        super().__init__(message)
        self.issue = issue


class BudgetExceededError(AgentFrameworkError):
    """Raised when runtime step or elapsed-time budget is exceeded."""
