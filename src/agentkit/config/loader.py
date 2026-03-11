"""Load and validate configuration from YAML/JSON."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from agentkit.config.provider_defaults import apply_provider_config_defaults
from agentkit.config.schema import (
    AgentConfig,
    AgentkitConfig,
    BudgetConfig,
    ProviderConfig,
    RunLogConfig,
    ToolConfig,
    WorkspaceConfig,
)
from agentkit.errors import ConfigError

_ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def load_config(
    path: str | Path,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> AgentkitConfig:
    """Load, merge, expand, and validate framework configuration."""
    config_path = Path(path).expanduser()
    raw = _read_raw_config(config_path)
    if overrides:
        raw = _deep_merge(raw, dict(overrides))
    raw = _expand_env(raw)

    try:
        workspace = WorkspaceConfig(**raw.get("workspace", {}))
        provider = ProviderConfig(**raw.get("provider", {}))
        budget = BudgetConfig(**raw.get("agent", {}).get("budget", {}))

        agent_data = dict(raw.get("agent", {}))
        agent_data.pop("budget", None)
        agent = AgentConfig(budget=budget, **agent_data)

        tools = ToolConfig(**raw.get("tools", {}))
        tools.entries = _resolve_tool_entries(
            tools.entries,
            base_dir=config_path.resolve(strict=False).parent,
        )
        runlog = RunLogConfig(**raw.get("runlog", {}))
    except TypeError as exc:
        raise ConfigError(f"Invalid configuration fields: {exc}") from exc

    apply_provider_config_defaults(provider)
    return AgentkitConfig(
        workspace=workspace,
        provider=provider,
        agent=agent,
        tools=tools,
        runlog=runlog,
    )


def _read_raw_config(path: str | Path) -> dict[str, Any]:
    """Read and parse a raw YAML/JSON configuration mapping."""
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config not found: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text) or {}
    elif suffix == ".json":
        loaded = json.loads(text)
    else:
        raise ConfigError(f"Unsupported config format: {config_path.suffix}")

    if not isinstance(loaded, dict):
        raise ConfigError("Root config must be a mapping/object.")
    return loaded


def _expand_env(value: Any) -> Any:
    """Recursively substitute ``${ENV_VAR}`` string placeholders."""
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value.strip())
        if match:
            return os.getenv(match.group(1))
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two mapping trees with ``override`` precedence."""
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], dict(value))
        else:
            merged[key] = value
    return merged


def _resolve_tool_entries(entries: list[str], *, base_dir: Path) -> list[str]:
    """Resolve configured tool entry paths relative to the config file."""
    resolved_entries: list[str] = []
    for entry in entries:
        candidate = Path(entry).expanduser()
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        resolved_entries.append(str(candidate.resolve(strict=False)))
    return resolved_entries
