"""Generic LLM agent framework."""

from __future__ import annotations

from pathlib import Path

from .agent.agent import Agent
from .config.loader import load_config
from .config.schema import AgentkitConfig


def create_agent(
    config_or_path: AgentkitConfig | str | Path,
) -> Agent:
    """Build an :class:`Agent` from config data or a config file.

    Args:
        config_or_path: Either a fully instantiated framework config object or a
            filesystem path to a YAML/JSON config file.

    Returns:
        Agent: A configured agent instance ready to execute tasks.

    Raises:
        agentkit.errors.ConfigError: If the config file is invalid or missing required
            fields.
    """
    if isinstance(config_or_path, AgentkitConfig):
        config = config_or_path
    else:
        config = load_config(config_or_path)
    return Agent.from_config(config)


__all__ = ["Agent", "AgentkitConfig", "create_agent", "load_config"]
