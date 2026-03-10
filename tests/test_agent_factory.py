from __future__ import annotations

from pathlib import Path

import pytest

import agentkit
from agentkit.config.schema import AgentkitConfig, ProviderConfig
from agentkit.errors import ConfigError
from agentkit.llm.factory import build_provider


def test_create_agent_uses_existing_config_object(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentkitConfig()
    sentinel = object()
    seen: dict[str, object] = {}

    def fake_from_config(cfg: AgentkitConfig) -> object:
        seen["config"] = cfg
        return sentinel

    monkeypatch.setattr(agentkit.Agent, "from_config", staticmethod(fake_from_config))

    created = agentkit.create_agent(config)

    assert created is sentinel
    assert seen["config"] is config


def test_create_agent_loads_from_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    loaded_config = AgentkitConfig()
    seen: dict[str, object] = {}

    def fake_load(path: Path) -> AgentkitConfig:
        seen["path"] = path
        return loaded_config

    monkeypatch.setattr(agentkit, "load_config", fake_load)
    monkeypatch.setattr(agentkit.Agent, "from_config", staticmethod(lambda cfg: cfg))

    config_path = tmp_path / "config.yaml"
    created = agentkit.create_agent(config_path)

    assert created is loaded_config
    assert seen["path"] == config_path


def test_build_provider_selects_expected_class(monkeypatch: pytest.MonkeyPatch) -> None:
    class MarkerProvider:
        def __init__(self, config: ProviderConfig) -> None:
            self.config = config

    monkeypatch.setattr("agentkit.llm.factory.OpenAIProvider", MarkerProvider)
    monkeypatch.setattr("agentkit.llm.factory.AnthropicProvider", MarkerProvider)
    monkeypatch.setattr("agentkit.llm.factory.GeminiProvider", MarkerProvider)
    monkeypatch.setattr("agentkit.llm.factory.VLLMProvider", MarkerProvider)
    monkeypatch.setattr("agentkit.llm.factory.QwenProvider", MarkerProvider)

    configs = [
        ProviderConfig(
            kind="openai", openai_api_variant="responses", api_key="test-openai-key"
        ),
        ProviderConfig(kind="anthropic", api_key="test-anthropic-key"),
        ProviderConfig(kind="gemini", api_key="test-gemini-key"),
        ProviderConfig(kind="vllm", openai_api_variant="chat_completions"),
        ProviderConfig(
            kind="qwen",
            openai_api_variant="chat_completions",
            api_key="test-qwen-key",
        ),
    ]
    for provider_config in configs:
        provider = build_provider(provider_config)
        assert isinstance(provider, MarkerProvider)
        assert provider.config is provider_config


def test_build_provider_rejects_unknown_kind() -> None:
    provider_config = ProviderConfig(kind="openai")
    provider_config.kind = "unknown"  # type: ignore[assignment]

    with pytest.raises(ConfigError, match="Unsupported provider kind"):
        build_provider(provider_config)
