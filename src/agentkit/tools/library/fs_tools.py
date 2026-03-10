"""Workspace-scoped filesystem tool bundle."""

from __future__ import annotations

from agentkit.tools.base import Tool
from agentkit.workspace.fs import WorkspaceFS

from .create_file import build_create_file_tool
from .str_replace import build_str_replace_tool
from .view import build_view_tool
from .word_count import build_word_count_tool


def build_tools(fs: WorkspaceFS) -> list[Tool]:
    """Create filesystem tools scoped to the workspace."""
    return [
        build_view_tool(fs),
        build_create_file_tool(fs),
        build_str_replace_tool(fs),
        build_word_count_tool(fs),
    ]
