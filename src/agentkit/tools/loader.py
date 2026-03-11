"""Automatic loading for built-in and user-provided tool modules."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import itertools
import pkgutil
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from agentkit.errors import ToolError
from agentkit.tools.base import Tool
from agentkit.workspace.fs import WorkspaceFS

TOOLS_LIBRARY_PACKAGE = "agentkit.tools.library"
_USER_TOOLS_PACKAGE_PREFIX = "_agentkit_user_tools"
_USER_TOOLS_COUNTER = itertools.count()


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


def load_tools_from_entries(
    entries: Iterable[str | Path], fs: WorkspaceFS
) -> list[Tool]:
    """Load tools from configured file or directory entries.

    Args:
        entries: Filesystem paths pointing to Python files or directories that
            contain Python tool modules.
        fs: Workspace filesystem injected into callable tool factories.

    Returns:
        list[Tool]: Flattened list of tools discovered from all configured entries.

    Raises:
        agentkit.errors.ToolError: If an entry is missing, unsupported, or does not
            define any tools.
    """
    loaded: list[Tool] = []
    package_names: dict[Path, str] = {}
    for entry in entries:
        path = Path(entry).expanduser().resolve(strict=False)
        loaded.extend(_load_tools_from_entry(path, fs, package_names=package_names))
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


def _load_tools_from_entry(
    path: Path,
    fs: WorkspaceFS,
    *,
    package_names: dict[Path, str],
) -> list[Tool]:
    """Load tools from one configured filesystem entry."""
    if not path.exists():
        raise ToolError(f"Tool entry not found: {path}")
    if path.is_file():
        return _load_tools_from_file_entry(path, fs, package_names=package_names)
    if path.is_dir():
        return _load_tools_from_directory_entry(path, fs, package_names=package_names)
    raise ToolError(f"Unsupported tool entry type: {path}")


def _load_tools_from_file_entry(
    path: Path,
    fs: WorkspaceFS,
    *,
    package_names: dict[Path, str],
) -> list[Tool]:
    """Load tools from one Python file entry."""
    if path.suffix != ".py":
        raise ToolError(f"Tool entry file must be a Python module: {path}")

    package_name = _ensure_entry_package(path.parent, package_names=package_names)
    module_name = f"{package_name}.{_sanitize_module_name(path.stem)}"
    module = _load_module_from_path(path, module_name=module_name)
    tools = _load_from_module(module, fs, module_name=str(path))
    if not tools:
        raise ToolError(f"Tool entry did not define any tools: {path}")
    return tools


def _load_tools_from_directory_entry(
    path: Path,
    fs: WorkspaceFS,
    *,
    package_names: dict[Path, str],
) -> list[Tool]:
    """Load tools from all eligible Python modules in one directory entry."""
    package_name = _ensure_entry_package(path, package_names=package_names)
    package_module = sys.modules[package_name]
    loaded = _load_from_module(package_module, fs, module_name=str(path / "__init__.py"))

    for child in sorted(path.iterdir(), key=lambda item: item.name):
        if not child.is_file():
            continue
        if child.suffix != ".py":
            continue
        if child.name == "__init__.py" or child.name.startswith("_"):
            continue
        module_name = f"{package_name}.{_sanitize_module_name(child.stem)}"
        module = _load_module_from_path(child, module_name=module_name)
        loaded.extend(_load_from_module(module, fs, module_name=str(child)))

    if not loaded:
        raise ToolError(f"Tool entry did not define any tools: {path}")
    return loaded


def _ensure_entry_package(path: Path, *, package_names: dict[Path, str]) -> str:
    """Create or reuse a synthetic package namespace for one filesystem root."""
    root = path.resolve(strict=False)
    existing = package_names.get(root)
    if existing is not None:
        return existing

    package_name = _next_dynamic_package_name(root)
    init_file = root / "__init__.py"
    if init_file.is_file():
        _load_module_from_path(
            init_file,
            module_name=package_name,
            submodule_search_locations=[str(root)],
        )
    else:
        module = ModuleType(package_name)
        module.__file__ = str(root)
        module.__package__ = package_name
        module.__path__ = [str(root)]  # type: ignore[attr-defined]
        spec = ModuleSpec(package_name, loader=None, is_package=True)
        spec.submodule_search_locations = [str(root)]
        module.__spec__ = spec
        sys.modules[package_name] = module

    package_names[root] = package_name
    return package_name


def _load_module_from_path(
    path: Path,
    *,
    module_name: str,
    submodule_search_locations: list[str] | None = None,
) -> ModuleType:
    """Import one Python file from disk under a caller-controlled module name."""
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
        submodule_search_locations=submodule_search_locations,
    )
    if spec is None or spec.loader is None:
        raise ToolError(f"Could not create an import spec for tool module: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ToolError(f"Failed to import tool module '{path}': {exc}") from exc
    return module


def _next_dynamic_package_name(path: Path) -> str:
    """Return a unique synthetic package name for one configured tool root."""
    suffix = next(_USER_TOOLS_COUNTER)
    slug = _sanitize_module_name(path.stem or "entry")
    return f"{_USER_TOOLS_PACKAGE_PREFIX}_{suffix}_{slug}"


def _sanitize_module_name(name: str) -> str:
    """Normalize arbitrary filenames into valid Python identifier segments."""
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    if not cleaned:
        return "tool_module"
    if cleaned[0].isdigit():
        return f"_{cleaned}"
    return cleaned
