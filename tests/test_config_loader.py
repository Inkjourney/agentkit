from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentkit.config.loader import _deep_merge, _expand_env, _read_raw_config, load_config
from agentkit.config.provider_defaults import DEFAULT_VLLM_BASE_URL
from agentkit.errors import ConfigError


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_read_raw_config_supports_yaml_and_json(tmp_path: Path) -> None:
    yaml_path = _write(
        tmp_path / "config.yaml",
        "workspace:\n  root: ./ws\nprovider:\n  kind: openai\n",
    )
    json_path = _write(
        tmp_path / "config.json",
        json.dumps({"workspace": {"root": "./ws"}, "provider": {"kind": "openai"}}),
    )

    yaml_data = _read_raw_config(yaml_path)
    json_data = _read_raw_config(json_path)

    assert yaml_data["workspace"]["root"] == "./ws"
    assert json_data["provider"]["kind"] == "openai"


def test_read_raw_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config not found"):
        _read_raw_config(tmp_path / "missing.yaml")


def test_read_raw_config_rejects_unsupported_suffix(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.txt", "provider: {}")
    with pytest.raises(ConfigError, match="Unsupported config format"):
        _read_raw_config(path)


def test_read_raw_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.json", json.dumps([1, 2, 3]))
    with pytest.raises(ConfigError, match="Root config must be a mapping"):
        _read_raw_config(path)


def test_expand_env_only_replaces_uppercase_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "secret")
    value = {
        "a": "${MY_KEY}",
        "b": [{"nested": "${MY_KEY}"}],
        "c": "${lower_case}",
        "d": "prefix-${MY_KEY}",
    }

    expanded = _expand_env(value)

    assert expanded["a"] == "secret"
    assert expanded["b"][0]["nested"] == "secret"
    assert expanded["c"] == "${lower_case}"
    assert expanded["d"] == "prefix-${MY_KEY}"


def test_deep_merge_overrides_nested_values() -> None:
    base: dict[str, Any] = {
        "agent": {"budget": {"max_steps": 5, "time_budget_s": 30}},
        "tools": {"allowed": ["a"]},
    }
    override: dict[str, Any] = {
        "agent": {"budget": {"max_steps": 9}},
        "tools": {"allowed": ["a", "b"]},
    }

    merged = _deep_merge(base, override)

    assert merged["agent"]["budget"]["max_steps"] == 9
    assert merged["agent"]["budget"]["time_budget_s"] == 30
    assert merged["tools"]["allowed"] == ["a", "b"]


def test_load_config_merges_overrides_and_injects_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    path = _write(
        tmp_path / "config.yaml",
        """
workspace:
  root: ./custom-workspace
provider:
  kind: openai
  openai_api_variant: responses
agent:
  system_prompt: base-prompt
  budget:
    max_steps: 2
tools:
  allowed: ["view"]
""".strip()
        + "\n",
    )

    config = load_config(
        path,
        overrides={
            "agent": {"budget": {"max_steps": 3}, "system_prompt": "override-prompt"},
            "runlog": {"max_text_chars": 1234},
        },
    )

    assert config.workspace.root == "./custom-workspace"
    assert config.agent.system_prompt == "override-prompt"
    assert config.agent.budget.max_steps == 3
    assert config.tools.allowed == ["view"]
    assert config.provider.api_key == "env-openai-key"
    assert config.runlog.max_text_chars == 1234


def test_load_config_respects_api_key_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOM_PROVIDER_KEY", "custom-key")
    path = _write(
        tmp_path / "config.yaml",
        """
provider:
  kind: anthropic
  api_key_env: CUSTOM_PROVIDER_KEY
""".strip()
        + "\n",
    )

    config = load_config(path)

    assert config.provider.api_key == "custom-key"


def test_load_config_qwen_uses_dashscope_default_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    path = _write(
        tmp_path / "config.yaml",
        """
provider:
  kind: qwen
  openai_api_variant: chat_completions
""".strip()
        + "\n",
    )

    config = load_config(path)

    assert config.provider.api_key == "dashscope-key"


def test_load_config_vllm_uses_local_defaults(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "config.yaml",
        """
provider:
  kind: vllm
  openai_api_variant: chat_completions
""".strip()
        + "\n",
    )

    config = load_config(path)

    assert config.provider.api_key is None
    assert config.provider.base_url == DEFAULT_VLLM_BASE_URL


def test_load_config_raises_when_api_key_missing(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.yaml", "provider:\n  kind: gemini\n")

    with pytest.raises(ConfigError, match="Missing API key"):
        load_config(path)


def test_load_config_wraps_unknown_fields_as_config_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "config.yaml",
        """
provider:
  kind: openai
  unknown_field: 123
""".strip()
        + "\n",
    )

    with pytest.raises(ConfigError, match="Invalid configuration fields"):
        load_config(path)
