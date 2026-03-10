from __future__ import annotations

import pytest

from agentkit.config.schema import BudgetConfig, ProviderConfig, RunLogConfig
from agentkit.errors import ConfigError


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_s": 0}, "timeout_s"),
        ({"retries": -1}, "retries"),
        ({"kind": "unsupported"}, "kind"),
        ({"openai_api_variant": "invalid"}, "openai_api_variant"),
        ({"conversation_mode": "invalid"}, "conversation_mode"),
        ({"thinking_budget": 0}, "thinking_budget"),
        (
            {"kind": "vllm", "openai_api_variant": "responses"},
            "kind=vllm must be 'chat_completions'",
        ),
        (
            {"kind": "qwen", "openai_api_variant": "responses"},
            "kind=qwen must be 'chat_completions'",
        ),
        (
            {"kind": "gemini", "openai_api_variant": "chat_completions"},
            "only configurable for kind=openai",
        ),
        (
            {
                "kind": "openai",
                "openai_api_variant": "chat_completions",
                "conversation_mode": "server",
            },
            "only supported for kind=openai with openai_api_variant='responses'",
        ),
    ],
)
def test_provider_config_rejects_invalid_values(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        ProviderConfig(**kwargs)


@pytest.mark.parametrize(
    "config",
    [
        ProviderConfig(kind="openai", openai_api_variant="responses", conversation_mode="auto"),
        ProviderConfig(kind="openai", openai_api_variant="chat_completions"),
        ProviderConfig(kind="openai", openai_api_variant="responses", conversation_mode="server"),
        ProviderConfig(kind="anthropic"),
        ProviderConfig(kind="gemini"),
        ProviderConfig(kind="vllm", openai_api_variant="chat_completions"),
        ProviderConfig(kind="qwen", openai_api_variant="chat_completions"),
        ProviderConfig(
            kind="qwen",
            openai_api_variant="chat_completions",
            thinking_budget=4096,
        ),
    ],
)
def test_provider_config_accepts_supported_combinations(config: ProviderConfig) -> None:
    assert config.timeout_s > 0
    assert config.retries >= 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_steps": 0}, "max_steps"),
        ({"time_budget_s": 0}, "time_budget_s"),
        ({"max_input_chars": 0}, "max_input_chars"),
    ],
)
def test_budget_config_rejects_invalid_values(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        BudgetConfig(**kwargs)


def test_budget_config_accepts_positive_values() -> None:
    config = BudgetConfig(max_steps=3, time_budget_s=10, max_input_chars=500)
    assert config.max_steps == 3
    assert config.time_budget_s == 10
    assert config.max_input_chars == 500


def test_runlog_config_rejects_non_positive_text_limit() -> None:
    with pytest.raises(ConfigError, match="max_text_chars"):
        RunLogConfig(max_text_chars=0)


def test_runlog_config_accepts_positive_text_limit() -> None:
    config = RunLogConfig(enabled=True, redact=True, max_text_chars=10)
    assert config.max_text_chars == 10
