"""View tool implementation."""

from __future__ import annotations

from typing import Any

from agentkit.errors import WorkspaceError
from agentkit.tools.base import FunctionTool, Tool
from agentkit.tools.types import ToolInvocation
from agentkit.workspace.fs import WorkspaceFS

from ._fs_common import (
    decode_text_for_view,
    error_payload,
    format_count,
    format_human_size,
    format_numbered_lines,
    format_path_workspace_error,
    is_probably_binary,
    list_directory_entries,
    normalize_view_range,
    path_details,
    split_lines,
)

_MAX_VIEW_MODEL_LINES = 250
_MAX_VIEW_DIRECTORY_ENTRIES = 50


def build_view_tool(fs: WorkspaceFS) -> Tool:
    """Build the workspace-bound ``view`` tool."""
    return FunctionTool(
        name="view",
        description=(
            "Read the content of a file or list the structure of a directory within the workspace.\n"
            "\n"
            "USE THIS TOOL WHEN you need to:\n"
            "- Read any text file: drafts, articles, outlines, notes, config files, etc.\n"
            "- Explore the workspace folder structure to understand how materials are organized.\n"
            "- Re-read a specific section of a long document before making edits or continuing work.\n"
            "\n"
            "BEHAVIOR:\n"
            "- For FILES: returns the content with right-aligned 1-based line numbers prefixed "
            "to each line (e.g. ' 1: ...', '12: ...'). UTF-8 is natively supported; non-UTF-8 "
            "bytes are escaped.\n"
            "  Use `view_range` to read only a specific section — recommended for long documents.\n"
            "- For DIRECTORIES: returns a sorted list of entries (files and subdirectories) up to "
            "2 levels deep. Hidden files (dotfiles) are excluded.\n"
            "\n"
            "IMPORTANT GUIDELINES:\n"
            "- ALWAYS read the relevant section of a file before editing it. "
            "Do not rely on memory — the file may have changed since you last saw it.\n"
            "- For long documents, prefer reading specific line ranges rather than the entire file.\n"
            "\n"
            "LIMITATIONS:\n"
            "- The path must exist inside the workspace; otherwise an error is raised.\n"
            "- Symlinks that escape the workspace boundary are silently skipped in directory listings."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A short explanation of WHY you are viewing this path. Be specific. "
                        "Good: 'Re-read the conclusion section before revising it'. "
                        "Bad: 'view file'."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path (from workspace root) to the file or directory to view. "
                        "Examples: 'draft.md', 'chapters/03.md', 'notes/'. "
                        "Must point to an existing file or directory."
                    ),
                },
                "view_range": {
                    "type": "array",
                    "description": (
                        "Optional. A two-element array [start_line, end_line] to read only a portion of a file. "
                        "Both values are 1-based and inclusive. Use -1 for end_line to read through the end of file. "
                        "Only valid for files (not directories). Omit to read the entire file. "
                        "Example: [50, 100] reads lines 50–100; [200, -1] reads from line 200 to the end."
                    ),
                },
            },
            "required": ["description", "path"],
            "additionalProperties": False,
        },
        handler=lambda args: _view(fs, args),
        success_formatter=_format_view_output,
        error_formatter=_format_view_error,
    )


def _view(fs: WorkspaceFS, args: dict[str, Any]) -> dict[str, Any]:
    """Return normalized file content or directory entries for a workspace path."""
    path = args["path"]
    target = fs.resolve_path(path)
    if not target.exists():
        raise WorkspaceError(f"Path does not exist: {path}")
    if target.is_dir():
        entries = list_directory_entries(fs, target)
        return {
            "path": path,
            "kind": "directory",
            "entries": entries,
            "directory_count": sum(1 for entry in entries if entry["kind"] == "directory"),
            "file_count": sum(1 for entry in entries if entry["kind"] == "file"),
        }
    if not target.is_file():
        raise WorkspaceError(f"Not a file or directory: {path}")
    data = target.read_bytes()
    if is_probably_binary(data):
        raise WorkspaceError(
            f"File appears to be binary and cannot be displayed as text: {path}"
        )
    text, encoding = decode_text_for_view(data)
    lines = split_lines(text)
    start_line, end_line = normalize_view_range(args.get("view_range"), len(lines))
    selected_lines = lines[start_line - 1 : end_line] if lines else []
    content = format_numbered_lines(
        selected_lines,
        start_line=start_line,
        total_lines=len(lines),
    )
    return {
        "path": path,
        "kind": "file",
        "start_line": start_line if lines else 0,
        "end_line": end_line if lines else 0,
        "total_lines": len(lines),
        "size_bytes": len(data),
        "encoding": encoding,
        "lines": selected_lines,
        "content": content,
    }


def _format_view_output(output: Any, invocation: ToolInvocation) -> Any:
    """Convert raw ``view`` results into model-facing display text."""
    if not isinstance(output, dict):
        return output
    kind = output.get("kind")
    if kind == "file":
        return _format_view_file_output(output, invocation)
    if kind == "directory":
        return _format_view_directory_output(output)
    return {"output": output}


def _format_view_file_output(
    output: dict[str, Any], invocation: ToolInvocation
) -> str | dict[str, Any]:
    """Render file output with headers, line numbers, and truncation notes."""
    path = output.get("path")
    total_lines = output.get("total_lines")
    size_bytes = output.get("size_bytes")
    start_line = output.get("start_line")
    end_line = output.get("end_line")
    lines = output.get("lines")
    if not (
        isinstance(path, str)
        and isinstance(total_lines, int)
        and isinstance(size_bytes, int)
        and isinstance(start_line, int)
        and isinstance(end_line, int)
        and isinstance(lines, list)
        and all(isinstance(line, str) for line in lines)
    ):
        return {"output": output}

    requested_range = invocation.arguments.get("view_range") if isinstance(
        invocation.arguments, dict
    ) else None
    is_range_view = requested_range is not None

    if total_lines == 0:
        header = f"File: {path} ({format_count(0, 'line')}, {format_human_size(size_bytes)})"
        return f"{header}\n---\n(empty file)\n---"

    displayed_lines = list(lines)
    displayed_start = start_line
    displayed_end = end_line
    note: str | None = None
    if len(displayed_lines) > _MAX_VIEW_MODEL_LINES:
        # Keep the payload bounded so a large file view does not crowd out the
        # rest of the conversation context. The note tells the model how to ask
        # for a narrower slice.
        displayed_lines = displayed_lines[:_MAX_VIEW_MODEL_LINES]
        displayed_end = displayed_start + len(displayed_lines) - 1
        if is_range_view:
            note = (
                f"(Showing lines {displayed_start}-{displayed_end} of requested range "
                f"{start_line}-{end_line}. Use a smaller view_range to narrow the result.)"
            )
        else:
            note = (
                f"(Showing lines {displayed_start}-{displayed_end} of {total_lines}. "
                "Use view with view_range to see more.)"
            )
    elif not is_range_view and total_lines > _MAX_VIEW_MODEL_LINES:
        displayed_lines = displayed_lines[:_MAX_VIEW_MODEL_LINES]
        displayed_end = displayed_start + len(displayed_lines) - 1
        note = (
            f"(Showing lines {displayed_start}-{displayed_end} of {total_lines}. "
            "Use view with view_range to see more.)"
        )

    if is_range_view:
        header = f"File: {path} | Lines {start_line}-{end_line} (of {total_lines})"
    else:
        header = (
            f"File: {path} ({format_count(total_lines, 'line')}, "
            f"{format_human_size(size_bytes)})"
        )

    body = format_numbered_lines(
        displayed_lines,
        start_line=displayed_start,
        total_lines=total_lines,
    )
    if note:
        return f"{header}\n---\n{body}\n---\n{note}"
    return f"{header}\n---\n{body}\n---"


def _format_view_directory_output(output: dict[str, Any]) -> str | dict[str, Any]:
    """Render directory listings as a compact tree with summary counts."""
    path = output.get("path")
    entries = output.get("entries")
    directory_count = output.get("directory_count")
    file_count = output.get("file_count")
    if not (
        isinstance(path, str)
        and isinstance(entries, list)
        and isinstance(directory_count, int)
        and isinstance(file_count, int)
    ):
        return {"output": output}

    displayed_entries = [
        entry for entry in entries[:_MAX_VIEW_DIRECTORY_ENTRIES] if isinstance(entry, dict)
    ]
    tree = _format_directory_tree(path, displayed_entries)
    header = (
        f"Directory: {_display_directory_path(path)} "
        f"({format_count(directory_count, 'subdirectory', 'subdirectories')}, "
        f"{format_count(file_count, 'file')})"
    )
    if len(entries) > _MAX_VIEW_DIRECTORY_ENTRIES:
        note = (
            f"(Showing first {_MAX_VIEW_DIRECTORY_ENTRIES} entries of {len(entries)}. "
            "Directory too large to display fully.)"
        )
        return f"{header}\n---\n{tree}\n{note}\n---"
    return f"{header}\n---\n{tree}\n---"


def _format_directory_tree(path: str, entries: list[dict[str, Any]]) -> str:
    """Convert flattened directory entries into a printable tree."""
    root: dict[str, Any] = {"children": {}}
    for entry in entries:
        entry_path = entry.get("path")
        kind = entry.get("kind")
        if not isinstance(entry_path, str) or not isinstance(kind, str):
            continue
        parts = [part for part in entry_path.split("/") if part]
        node = root
        for index, part in enumerate(parts):
            children = node.setdefault("children", {})
            child = children.setdefault(part, {"kind": "directory", "children": {}})
            if index == len(parts) - 1:
                child["kind"] = kind
            node = child

    lines = [_display_directory_path(path)]
    lines.extend(_render_tree_children(root.get("children", {}), prefix=""))
    return "\n".join(lines)


def _render_tree_children(children: dict[str, Any], *, prefix: str) -> list[str]:
    """Render one nested tree level using box-drawing characters."""
    lines: list[str] = []
    items = list(children.items())
    for index, (name, node) in enumerate(items):
        is_last = index == len(items) - 1
        connector = "└──" if is_last else "├──"
        kind = node.get("kind")
        suffix = "/" if kind == "directory" else ""
        lines.append(f"{prefix}{connector} {name}{suffix}")
        child_children = node.get("children", {})
        if isinstance(child_children, dict) and child_children:
            next_prefix = prefix + ("    " if is_last else "│   ")
            lines.extend(_render_tree_children(child_children, prefix=next_prefix))
    return lines


def _display_directory_path(path: str) -> str:
    """Normalize the root label shown for directory listings."""
    if path in {".", "./"}:
        return "./"
    return path if path.endswith("/") else f"{path}/"


def _format_view_error(error: Exception, invocation: ToolInvocation) -> dict[str, Any]:
    """Translate ``view`` failures into stable model-facing errors."""
    common = format_path_workspace_error(
        error,
        invocation,
        missing_message="The requested path does not exist in the workspace.",
        missing_hint="Call `view` again with an existing file or directory path.",
        not_dir_or_file_message="The requested path is neither a regular file nor a directory.",
    )
    if common is not None:
        return common

    message = str(error)
    details = path_details(invocation)
    if message.startswith("File appears to be binary and cannot be displayed as text: "):
        return error_payload(
            "binary_file",
            "This file appears to be binary and cannot be viewed as text.",
            hint="Use a text file path, or choose a different tool if you only need file metadata.",
            details=details,
        )
    if message == "Cannot apply view_range to an empty file.":
        return error_payload(
            "empty_file",
            "The file is empty, so a line range cannot be applied.",
            hint="Call `view` again without `view_range`, or choose a non-empty file.",
            details=details,
        )
    if message.startswith("start_line ") and "is beyond the end of file" in message:
        return error_payload(
            "view_range_out_of_bounds",
            message,
            hint="Choose a start_line within the file's total line count.",
            details=details,
        )
    if message == "view_range must be a two-item array: [start_line, end_line].":
        return error_payload(
            "invalid_view_range",
            "view_range must be a two-item array: [start_line, end_line].",
            hint="Provide both start_line and end_line, for example [10, 20].",
            details=details,
        )
    if message == "view_range values must both be integers.":
        return error_payload(
            "invalid_view_range_type",
            "view_range values must both be integers.",
            hint="Use integer line numbers such as [1, 50].",
            details=details,
        )
    if message == "start_line must be >= 1.":
        return error_payload(
            "invalid_view_range",
            "start_line must be at least 1.",
            hint="Use 1-based line numbers.",
            details=details,
        )
    if message == "end_line must be -1 or >= start_line." or (
        message.startswith("end_line ") and "must be -1 or >= start_line" in message
    ):
        return error_payload(
            "invalid_view_range",
            "end_line must be -1 or greater than or equal to start_line.",
            hint="Use -1 to read to the end of the file, or choose an end_line after start_line.",
            details=details,
        )
    return error_payload("view_failed", message, details=details)
