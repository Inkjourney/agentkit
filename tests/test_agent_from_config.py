from __future__ import annotations

from pathlib import Path
import textwrap

import pytest

from agentkit.agent.agent import Agent
from agentkit.config.schema import AgentkitConfig
from agentkit.tools.base import FunctionTool


def test_agent_from_config_wires_runtime_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = object()
    created_roots: list[Path] = []

    def fake_init_workspace_layout(root: str) -> Path:
        resolved = (tmp_path / root).resolve()
        created_roots.append(resolved)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    monkeypatch.setattr("agentkit.agent.agent.init_workspace_layout", fake_init_workspace_layout)
    monkeypatch.setattr(
        "agentkit.agent.agent.build_provider", lambda _provider_config: provider
    )
    monkeypatch.setattr(
        "agentkit.agent.agent.load_tools_from_library",
        lambda _fs: [
            FunctionTool(
                name="demo_tool",
                description="Demo",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=lambda _args: "ok",
            )
        ],
    )

    config = AgentkitConfig()
    config.workspace.root = "agent-workspace"
    config.tools.allowed = ["demo_tool"]
    agent = Agent.from_config(config)

    assert created_roots
    assert agent.provider is provider
    assert agent.fs.root == created_roots[0]
    assert [schema.name for schema in agent.tool_runtime.schemas()] == ["demo_tool"]


def test_agent_from_config_loads_tools_from_configured_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider = object()

    def fake_init_workspace_layout(root: str) -> Path:
        resolved = (tmp_path / root).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    tool_file = tmp_path / "custom_tools.py"
    tool_file.write_text(
        textwrap.dedent(
            """
            from agentkit.tools.base import FunctionTool

            TOOLS = [
                FunctionTool(
                    name="slugify",
                    description="Slugify text",
                    parameters={
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    handler=lambda args: {"slug": args["text"].lower().replace(" ", "-")},
                )
            ]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("agentkit.agent.agent.init_workspace_layout", fake_init_workspace_layout)
    monkeypatch.setattr(
        "agentkit.agent.agent.build_provider", lambda _provider_config: provider
    )
    monkeypatch.setattr("agentkit.agent.agent.load_tools_from_library", lambda _fs: [])

    config = AgentkitConfig()
    config.workspace.root = "agent-workspace"
    config.tools.entries = [str(tool_file)]
    config.tools.allowed = ["slugify"]

    agent = Agent.from_config(config)

    assert agent.provider is provider
    assert [schema.name for schema in agent.tool_runtime.schemas()] == ["slugify"]
