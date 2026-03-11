"""Dataclass schemas for runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agentkit.constants import (
    DEFAULT_MAX_INPUT_CHARS,
    DEFAULT_MAX_STEPS,
    DEFAULT_TIME_BUDGET_S,
)
from agentkit.errors import ConfigError


@dataclass(slots=True)
class WorkspaceConfig:
    """Workspace-level settings."""

    root: str = "./workspace"


ProviderKind = Literal["openai", "anthropic", "gemini", "vllm", "qwen"]
OpenAIApiVariant = Literal["responses", "chat_completions"]
ConversationMode = Literal["auto", "client", "server"]


@dataclass(slots=True)
class ProviderConfig:
    """LLM provider configuration."""

    kind: ProviderKind = "openai"
    model: str = "gpt-5"
    openai_api_variant: OpenAIApiVariant = "responses"
    conversation_mode: ConversationMode = "auto"
    temperature: float | None = 0.2
    timeout_s: int = 60
    retries: int = 2
    api_key: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    reasoning_effort: str | None = None
    enable_thinking: bool = True
    thinking_budget: int | None = None

    def __post_init__(self) -> None:
        """Validate provider-specific invariants and cross-field combinations."""
        if self.timeout_s <= 0:
            raise ConfigError("provider.timeout_s must be > 0")
        if self.retries < 0:
            raise ConfigError("provider.retries must be >= 0")
        if self.kind not in {"openai", "anthropic", "gemini", "vllm", "qwen"}:
            raise ConfigError(f"Unsupported provider kind: {self.kind}")
        if self.thinking_budget is not None and self.thinking_budget <= 0:
            raise ConfigError("provider.thinking_budget must be > 0 when provided.")

        if self.openai_api_variant not in {"responses", "chat_completions"}:
            raise ConfigError(
                "provider.openai_api_variant must be 'responses' or 'chat_completions'."
            )
        if self.conversation_mode not in {"auto", "client", "server"}:
            raise ConfigError(
                "provider.conversation_mode must be 'auto', 'client', or 'server'."
            )

        if (
            self.kind in {"anthropic", "gemini"}
            and self.openai_api_variant != "responses"
        ):
            raise ConfigError(
                "provider.openai_api_variant is only configurable for kind=openai; "
                "kind=anthropic/gemini do not use it."
            )

        if (
            self.kind in {"vllm", "qwen"}
            and self.openai_api_variant != "chat_completions"
        ):
            raise ConfigError(
                f"provider.openai_api_variant for kind={self.kind} must be 'chat_completions'."
            )

        if self.conversation_mode == "server" and not (
            self.kind == "openai" and self.openai_api_variant == "responses"
        ):
            raise ConfigError(
                "provider.conversation_mode='server' is only supported for "
                "kind=openai with openai_api_variant='responses'."
            )


@dataclass(slots=True)
class BudgetConfig:
    """Runtime budget limits for one task execution."""

    max_steps: int = DEFAULT_MAX_STEPS
    time_budget_s: int = DEFAULT_TIME_BUDGET_S
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS

    def __post_init__(self) -> None:
        """Validate that each configured runtime limit is strictly positive."""
        if self.max_steps <= 0:
            raise ConfigError("agent.budget.max_steps must be > 0")
        if self.time_budget_s <= 0:
            raise ConfigError("agent.budget.time_budget_s must be > 0")
        if self.max_input_chars <= 0:
            raise ConfigError("agent.budget.max_input_chars must be > 0")


@dataclass(slots=True)
class AgentConfig:
    """Agent behavior configuration."""

    system_prompt: str = "You are a helpful agent. Use tools when needed."
    budget: BudgetConfig = field(default_factory=BudgetConfig)


@dataclass(slots=True)
class ToolConfig:
    """Tool exposure configuration."""

    allowed: list[str] = field(default_factory=list)
    entries: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate allowlist and external entry shapes."""
        if not isinstance(self.allowed, list) or any(
            not isinstance(name, str) or not name.strip() for name in self.allowed
        ):
            raise ConfigError("tools.allowed must be a list of non-empty strings.")
        if not isinstance(self.entries, list) or any(
            not isinstance(entry, str) or not entry.strip() for entry in self.entries
        ):
            raise ConfigError("tools.entries must be a list of non-empty strings.")


@dataclass(slots=True)
class RunLogConfig:
    """Run log projection settings."""

    enabled: bool = True
    redact: bool = True
    max_text_chars: int = 20_000

    def __post_init__(self) -> None:
        """Validate redaction and truncation settings for run-log output."""
        if self.max_text_chars <= 0:
            raise ConfigError("runlog.max_text_chars must be > 0")


@dataclass(slots=True)
class AgentkitConfig:
    """Top-level configuration container."""

    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    runlog: RunLogConfig = field(default_factory=RunLogConfig)
