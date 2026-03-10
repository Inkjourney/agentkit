"""Automatic tool loading from the tool library directory."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any, Iterable

from agentkit.errors import ToolError
from agentkit.tools.base import Tool
from agentkit.workspace.fs import WorkspaceFS

TOOLS_LIBRARY_PACKAGE = "agentkit.tools.library"


def load_tools_from_library(fs: WorkspaceFS) -> list[Tool]:
    """Load all tools exposed by modules under ``agentkit.tools.library``.

    Tool modules can expose tools via:
    - ``build_tools(fs)`` (or ``build_tools()``)
    - ``TOOLS`` module variable

    Args:
        fs: Workspace filesystem injected into callable tool factories.

    Returns:
        list[Tool]: Flattened list of tools from all library modules.
    """
    package = importlib.import_module(TOOLS_LIBRARY_PACKAGE)
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return []

    loaded: list[Tool] = []
    for module_info in sorted(pkgutil.iter_modules(package_path), key=lambda m: m.name):
        if module_info.name.startswith("_"):
            continue
        module_name = f"{TOOLS_LIBRARY_PACKAGE}.{module_info.name}"
        module = importlib.import_module(module_name)
        loaded.extend(_load_from_module(module, fs, module_name=module_name))
    return loaded


def _load_from_module(module: Any, fs: WorkspaceFS, *, module_name: str) -> list[Tool]:
    """Extract tools from one library module."""
    if hasattr(module, "build_tools"):
        return _coerce_to_tools(getattr(module, "build_tools"), fs, module_name)
    if hasattr(module, "TOOLS"):
        return _coerce_to_tools(getattr(module, "TOOLS"), fs, module_name)
    return []


def _coerce_to_tools(candidate: Any, fs: WorkspaceFS, module_name: str) -> list[Tool]:
    """Normalize supported tool declarations into ``list[Tool]``."""
    if isinstance(candidate, Tool):
        return [candidate]

    if callable(candidate):
        built: Any
        try:
            signature = inspect.signature(candidate)
            if len(signature.parameters) == 0:
                built = candidate()
            else:
                built = candidate(fs)
        except ValueError:
            built = candidate(fs)
        return _coerce_to_tools(built, fs, module_name)

    if isinstance(candidate, Iterable) and not isinstance(
        candidate, (str, bytes, dict)
    ):
        tools = list(candidate)
        if all(isinstance(item, Tool) for item in tools):
            return tools

    raise ToolError(
        f"Module '{module_name}' must expose Tool, Iterable[Tool], build_tools(...), or TOOLS."
    )

