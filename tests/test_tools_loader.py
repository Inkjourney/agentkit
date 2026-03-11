from __future__ import annotations

import pkgutil
from pathlib import Path
import textwrap
from types import SimpleNamespace

import pytest

from agentkit.errors import ToolError
from agentkit.tools.base import FunctionTool, Tool
from agentkit.tools.loader import (
    TOOLS_LIBRARY_PACKAGE,
    _coerce_to_tools,
    _load_from_module,
    load_tools_from_entries,
    load_tools_from_library,
)
from agentkit.workspace.fs import WorkspaceFS


def _tool(name: str = "sample") -> Tool:
    return FunctionTool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda _: {"name": name},
    )


def _write_module(path: Path, text: str) -> Path:
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
    return path


def test_coerce_to_tools_accepts_supported_shapes(workspace_fs: WorkspaceFS) -> None:
    tool = _tool()

    assert _coerce_to_tools(tool, workspace_fs, "m") == [tool]

    built_no_args = _coerce_to_tools(lambda: [tool], workspace_fs, "m")
    assert built_no_args == [tool]

    seen: list[WorkspaceFS] = []

    def build_with_fs(fs: WorkspaceFS) -> list[Tool]:
        seen.append(fs)
        return [tool]

    built_with_fs = _coerce_to_tools(build_with_fs, workspace_fs, "m")
    assert built_with_fs == [tool]
    assert seen == [workspace_fs]

    iterable_built = _coerce_to_tools([tool], workspace_fs, "m")
    assert iterable_built == [tool]


def test_coerce_to_tools_rejects_invalid_shape(workspace_fs: WorkspaceFS) -> None:
    with pytest.raises(ToolError, match="must expose Tool"):
        _coerce_to_tools({"bad": "shape"}, workspace_fs, "invalid")

    with pytest.raises(ToolError, match="must expose Tool"):
        _coerce_to_tools([_tool(), object()], workspace_fs, "invalid")


def test_load_from_module_prefers_build_tools(workspace_fs: WorkspaceFS) -> None:
    primary = _tool("primary")
    fallback = _tool("fallback")
    module = SimpleNamespace(
        build_tools=lambda fs: [primary],
        TOOLS=[fallback],
    )

    loaded = _load_from_module(module, workspace_fs, module_name="demo.module")

    assert [tool.name for tool in loaded] == ["primary"]


def test_load_from_module_uses_tools_attribute_when_no_builder(
    workspace_fs: WorkspaceFS,
) -> None:
    module = SimpleNamespace(TOOLS=[_tool("a"), _tool("b")])

    loaded = _load_from_module(module, workspace_fs, module_name="demo.module")

    assert [tool.name for tool in loaded] == ["a", "b"]


def test_load_tools_from_library_discovers_and_sorts_modules(
    monkeypatch: pytest.MonkeyPatch, workspace_fs: WorkspaceFS
) -> None:
    package = SimpleNamespace(__path__=["/fake/library"])
    modules = {
        f"{TOOLS_LIBRARY_PACKAGE}.alpha": SimpleNamespace(TOOLS=[_tool("a1")]),
        f"{TOOLS_LIBRARY_PACKAGE}.beta": SimpleNamespace(TOOLS=[_tool("b1")]),
    }

    def fake_import_module(name: str) -> object:
        if name == TOOLS_LIBRARY_PACKAGE:
            return package
        return modules[name]

    monkeypatch.setattr(
        "agentkit.tools.loader.importlib.import_module", fake_import_module
    )
    monkeypatch.setattr(
        "agentkit.tools.loader.pkgutil.iter_modules",
        lambda _paths: [
            pkgutil.ModuleInfo(None, "_private", False),
            pkgutil.ModuleInfo(None, "beta", False),
            pkgutil.ModuleInfo(None, "alpha", False),
        ],
    )

    loaded = load_tools_from_library(workspace_fs)

    assert [tool.name for tool in loaded] == ["a1", "b1"]


def test_load_tools_from_library_returns_empty_without_package_path(
    monkeypatch: pytest.MonkeyPatch, workspace_fs: WorkspaceFS
) -> None:
    monkeypatch.setattr(
        "agentkit.tools.loader.importlib.import_module", lambda _name: SimpleNamespace()
    )

    assert load_tools_from_library(workspace_fs) == []


def test_load_tools_from_entries_loads_single_python_file(
    tmp_path: Path, workspace_fs: WorkspaceFS
) -> None:
    module_path = _write_module(
        tmp_path / "custom_tools.py",
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
        """,
    )

    loaded = load_tools_from_entries([module_path], workspace_fs)

    assert [tool.name for tool in loaded] == ["slugify"]


def test_load_tools_from_entries_discovers_python_modules_in_directory(
    tmp_path: Path, workspace_fs: WorkspaceFS
) -> None:
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    _write_module(
        tools_dir / "_helpers.py",
        """
        def unused() -> str:
            return "helper"
        """,
    )
    _write_module(
        tools_dir / "beta.py",
        """
        from agentkit.tools.base import FunctionTool

        TOOLS = [
            FunctionTool(
                name="beta_tool",
                description="Beta",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=lambda _args: {"ok": "beta"},
            )
        ]
        """,
    )
    _write_module(
        tools_dir / "alpha.py",
        """
        from agentkit.tools.base import FunctionTool

        TOOLS = [
            FunctionTool(
                name="alpha_tool",
                description="Alpha",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=lambda _args: {"ok": "alpha"},
            )
        ]
        """,
    )

    loaded = load_tools_from_entries([tools_dir], workspace_fs)

    assert [tool.name for tool in loaded] == ["alpha_tool", "beta_tool"]


def test_load_tools_from_entries_supports_relative_imports_within_directory(
    tmp_path: Path, workspace_fs: WorkspaceFS
) -> None:
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    _write_module(
        tools_dir / "_shared.py",
        """
        def slugify(text: str) -> str:
            return text.strip().lower().replace(" ", "-")
        """,
    )
    _write_module(
        tools_dir / "slugify.py",
        """
        from agentkit.tools.base import FunctionTool
        from ._shared import slugify

        def run(args: dict[str, str]) -> dict[str, str]:
            return {"slug": slugify(args["text"])}

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
                handler=run,
            )
        ]
        """,
    )

    loaded = load_tools_from_entries([tools_dir], workspace_fs)
    outcome = loaded[0].run({"text": "Agent Kit"})

    assert [tool.name for tool in loaded] == ["slugify"]
    assert outcome == {"slug": "agent-kit"}


def test_load_tools_from_entries_rejects_missing_path(
    tmp_path: Path, workspace_fs: WorkspaceFS
) -> None:
    missing = tmp_path / "missing.py"

    with pytest.raises(ToolError, match="Tool entry not found"):
        load_tools_from_entries([missing], workspace_fs)
