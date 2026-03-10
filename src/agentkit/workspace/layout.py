"""Workspace folder layout helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from agentkit.constants import DEFAULT_WORKSPACE_DIRS


def init_workspace_layout(
    root: str | Path,
    *,
    extra_dirs: Iterable[str] | None = None,
) -> Path:
    """Create default workspace directories under the given root.

    Args:
        root: Workspace root directory path.
        extra_dirs: Optional additional directory names to create.

    Returns:
        pathlib.Path: Resolved workspace root path.
    """
    root_path = Path(root).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)

    dirs = list(DEFAULT_WORKSPACE_DIRS)
    if extra_dirs:
        dirs.extend(extra_dirs)
    for item in dirs:
        (root_path / item).mkdir(parents=True, exist_ok=True)
    return root_path
