"""Provider-specific default metadata and normalization helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from agentkit.config.schema import ProviderConfig, ProviderKind
from agentkit.errors import ConfigError

DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_VLLM_BASE_URL = "http://localhost:8000/v1"

DEFAULT_API_KEY_ENV_BY_PROVIDER: dict[ProviderKind, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "vllm": "VLLM_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
}

DEFAULT_BASE_URL_BY_PROVIDER: dict[ProviderKind, str] = {
    "anthropic": DEFAULT_ANTHROPIC_BASE_URL,
    "gemini": DEFAULT_GEMINI_BASE_URL,
    "qwen": DEFAULT_QWEN_BASE_URL,
    "vllm": DEFAULT_VLLM_BASE_URL,
}


@dataclass(frozen=True)
class ProviderDefaults:
    """Resolved default metadata for one provider kind.

    Attributes:
        api_key_env: Default environment variable name for the API key.
        base_url: Default base URL when the provider has a fixed endpoint.
    """

    api_key_env: str
    base_url: str | None = None


def defaults_for_provider(kind: ProviderKind) -> ProviderDefaults:
    """Return the shared default metadata for one provider kind."""
    if kind not in DEFAULT_API_KEY_ENV_BY_PROVIDER:
        raise ConfigError(f"Unsupported provider kind: {kind}")
    return ProviderDefaults(
        api_key_env=DEFAULT_API_KEY_ENV_BY_PROVIDER[kind],
        base_url=DEFAULT_BASE_URL_BY_PROVIDER.get(kind),
    )


def apply_provider_config_defaults(
    config: ProviderConfig,
) -> ProviderConfig:
    """Mutate a provider config in place with shared defaults and env resolution.

    Args:
        config: Provider config to normalize.

    Returns:
        ProviderConfig: The same config object after normalization.

    Raises:
        agentkit.errors.ConfigError: If the provider still has no API key after
            applying defaults.
    """
    defaults = defaults_for_provider(config.kind)

    if not config.api_key_env:
        config.api_key_env = defaults.api_key_env
    if not config.base_url and defaults.base_url:
        config.base_url = defaults.base_url

    if config.api_key is None and config.api_key_env:
        config.api_key = os.getenv(config.api_key_env)

    if not config.api_key:
        if config.kind == "vllm" and is_localhost_base_url(config.base_url):
            return config
        env_name = config.api_key_env or defaults.api_key_env
        raise ConfigError(
            f"Missing API key. Set {env_name} or provider.api_key/provider.api_key_env in config."
        )

    return config


def is_localhost_base_url(base_url: str | None) -> bool:
    """Return whether the configured base URL targets a local development server."""
    if not base_url:
        return False
    lowered = base_url.lower()
    return "localhost" in lowered or "127.0.0.1" in lowered
