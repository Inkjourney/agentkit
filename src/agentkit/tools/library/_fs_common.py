"""Shared helpers for workspace-scoped filesystem tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.errors import ToolError, WorkspaceError
from agentkit.tools.types import ToolInvocation, ToolModelError
from agentkit.workspace.fs import WorkspaceFS

_MAX_VIEW_DEPTH = 2
_BINARY_CHECK_SIZE = 8192
_ALLOWED_TEXT_CONTROL_BYTES = {9, 10, 12, 13}
_SKIP_NAMES: frozenset[str] = frozenset({"node_modules", "__pycache__"})
_COUNTED_CJK_IDEOGRAPH_RANGES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x2F800, 0x2FA1F),
)
_COUNTED_CJK_PUNCTUATION_RANGES: tuple[tuple[int, int], ...] = (
    (0x3000, 0x303F),
    (0xFE30, 0xFE4F),
    (0xFF01, 0xFF0F),
    (0xFF1A, 0xFF20),
    (0xFF3B, 0xFF40),
    (0xFF5B, 0xFF65),
)
_EXCLUDED_PLATFORM_COUNT_RANGES: tuple[tuple[int, int], ...] = (
    (0x1100, 0x11FF),
    (0x3040, 0x309F),
    (0x30A0, 0x30FF),
    (0x31F0, 0x31FF),
    (0xA960, 0xA97F),
    (0xAC00, 0xD7AF),
    (0xD7B0, 0xD7FF),
    (0xFF65, 0xFF9F),
)


def error_payload(
    code: str,
    message: str,
    *,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical structured error payload returned to the model."""
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if hint:
        error["hint"] = hint
    if details:
        error["details"] = dict(details)
    return {"error": error}


def path_details(invocation: ToolInvocation) -> dict[str, Any]:
    """Extract path context from invocation arguments when it is available."""
    path = invocation.arguments.get("path") if isinstance(invocation.arguments, dict) else None
    if isinstance(path, str) and path:
        return {"path": path}
    return {}


def format_path_workspace_error(
    error: Exception,
    invocation: ToolInvocation,
    *,
    missing_message: str,
    missing_hint: str,
    not_file_message: str | None = None,
    not_dir_or_file_message: str | None = None,
) -> dict[str, Any] | None:
    """Translate common workspace path failures into stable tool error payloads."""
    if isinstance(error, ToolModelError):
        return error.to_model_payload()
    message = str(error)
    details = path_details(invocation)
    if message.startswith("Path escapes workspace: "):
        return error_payload(
            "path_outside_workspace",
            "The path must stay inside the workspace.",
            hint="Use a relative path inside the workspace root.",
            details=details,
        )
    if message.startswith("Path does not exist: ") or message.startswith("File does not exist: "):
        return error_payload(
            "path_not_found",
            missing_message,
            hint=missing_hint,
            details=details,
        )
    if not_dir_or_file_message and message.startswith("Not a file or directory: "):
        return error_payload(
            "invalid_path_kind",
            not_dir_or_file_message,
            hint="Choose an existing file or directory path that matches the tool's requirements.",
            details=details,
        )
    if not_file_message and message.startswith("Not a file: "):
        return error_payload(
            "not_a_file",
            not_file_message,
            hint="Choose an existing file path, not a directory.",
            details=details,
        )
    return None


def resolve_existing_file(fs: WorkspaceFS, path: str) -> Path:
    """Resolve ``path`` and ensure it exists as a regular file."""
    target = fs.resolve_path(path)
    if not target.exists():
        raise WorkspaceError(f"File does not exist: {path}")
    if not target.is_file():
        raise WorkspaceError(f"Not a file: {path}")
    return target


def read_utf8_text_for_edit(fs: WorkspaceFS, path: str) -> str:
    """Read an editable UTF-8 file or raise a workspace-scoped error."""
    target = resolve_existing_file(fs, path)
    try:
        return target.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError(f"File is not valid UTF-8 text: {path}") from exc


def decode_text_for_view(data: bytes) -> tuple[str, str]:
    """Decode file bytes for viewing, escaping undecodable bytes when needed."""
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="backslashreplace"), "utf-8/backslashreplace"


def normalize_view_range(view_range: Any, total_lines: int) -> tuple[int, int]:
    """Validate and normalize a 1-based inclusive file line range."""
    if view_range is None:
        if total_lines == 0:
            return 1, 0
        return 1, total_lines
    if not isinstance(view_range, (list, tuple)) or len(view_range) != 2:
        raise ToolError("view_range must be a two-item array: [start_line, end_line].")
    start_line, end_line = view_range
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        raise ToolError("view_range values must both be integers.")
    if start_line < 1:
        raise ToolError("start_line must be >= 1.")
    if end_line < -1:
        raise ToolError("end_line must be -1 or >= start_line.")
    if total_lines == 0:
        raise WorkspaceError("Cannot apply view_range to an empty file.")
    if start_line > total_lines:
        raise WorkspaceError(
            f"start_line {start_line} is beyond the end of file ({total_lines} lines)."
        )
    if end_line == -1 or end_line > total_lines:
        end_line = total_lines
    if end_line < start_line:
        raise WorkspaceError(
            f"end_line {end_line} must be -1 or >= start_line {start_line}."
        )
    return start_line, end_line


def split_lines(text: str) -> list[str]:
    """Split text into logical lines without inventing a trailing empty line."""
    return text.splitlines() if text else []


def format_numbered_lines(
    lines: list[str], *, start_line: int, total_lines: int | None = None
) -> str:
    """Prefix lines with right-aligned 1-based line numbers."""
    if not lines:
        return ""

    last_line_number = start_line + len(lines) - 1
    max_line_number = (
        max(total_lines, last_line_number, 1)
        if total_lines is not None
        else max(last_line_number, 1)
    )
    number_width = len(str(max_line_number))
    return "\n".join(
        f"{line_number:>{number_width}}: {line}"
        for line_number, line in enumerate(lines, start=start_line)
    )


def format_human_size(size_bytes: int) -> str:
    """Format a byte count for compact human-facing output."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    size = float(size_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}"
    return f"{size_bytes}B"


def format_count(value: int, singular: str, plural: str | None = None) -> str:
    """Format a singular/plural count phrase for status messages."""
    if value == 1:
        return f"1 {singular}"
    return f"{value} {plural or singular + 's'}"


def list_directory_entries(fs: WorkspaceFS, root: Path) -> list[dict[str, Any]]:
    """Collect directory entries up to the shared view depth limit."""
    entries: list[dict[str, Any]] = []
    _walk_directory(fs, root, root, depth=1, entries=entries)
    return sorted(entries, key=lambda entry: str(entry["path"]))


def _walk_directory(
    fs: WorkspaceFS,
    root: Path,
    current: Path,
    *,
    depth: int,
    entries: list[dict[str, Any]],
) -> None:
    """Recursively collect workspace-safe directory entries for tree rendering."""
    if depth > _MAX_VIEW_DEPTH:
        return
    for child in sorted(current.iterdir(), key=lambda item: item.name):
        if _should_skip_name(child.name):
            continue
        if not _is_within_workspace(child.resolve(strict=False), fs.root):
            continue
        rel_path = child.relative_to(root).as_posix()
        kind = "directory" if child.is_dir() else "file"
        entries.append({"path": rel_path, "kind": kind, "depth": depth})
        if child.is_dir():
            _walk_directory(fs, root, child, depth=depth + 1, entries=entries)


def _should_skip_name(name: str) -> bool:
    """Return whether a file or directory should be hidden from tool output."""
    return name.startswith(".") or name in _SKIP_NAMES


def _is_within_workspace(path: Path, root: Path) -> bool:
    """Return whether a resolved path stays under the workspace root."""
    return path.is_relative_to(root)


def is_probably_binary(data: bytes) -> bool:
    """Heuristically reject binary files before attempting text rendering."""
    if not data:
        return False
    sample = data[:_BINARY_CHECK_SIZE]
    if b"\x00" in sample:
        return True
    disallowed_controls = sum(
        1 for byte in sample if byte < 32 and byte not in _ALLOWED_TEXT_CONTROL_BYTES
    )
    return (disallowed_controls / len(sample)) > 0.05


def classify_counted_character(char: str) -> str | None:
    """Classify a character according to the platform-aligned count heuristic."""
    if char.isspace():
        return None

    code_point = ord(char)
    # Some scripts and punctuation are intentionally excluded because downstream
    # product metrics do not count them toward the "word_count" surfaced to users.
    if _is_in_code_point_ranges(code_point, _EXCLUDED_PLATFORM_COUNT_RANGES):
        return None
    if 0x21 <= code_point <= 0x7E:
        return "ascii_visible"
    if _is_in_code_point_ranges(code_point, _COUNTED_CJK_IDEOGRAPH_RANGES):
        return "cjk_ideograph"
    if _is_in_code_point_ranges(code_point, _COUNTED_CJK_PUNCTUATION_RANGES):
        return "cjk_punctuation"
    return None


def count_text_metrics(text: str) -> dict[str, int]:
    """Compute the text metrics returned by filesystem-oriented tools."""
    ascii_visible_char_count = 0
    cjk_ideograph_count = 0
    cjk_punctuation_count = 0
    for char in text:
        category = classify_counted_character(char)
        if category == "ascii_visible":
            ascii_visible_char_count += 1
        elif category == "cjk_ideograph":
            cjk_ideograph_count += 1
        elif category == "cjk_punctuation":
            cjk_punctuation_count += 1
    lines = split_lines(text)
    # The exposed "word_count" matches product expectations rather than natural
    # language tokenization: ASCII-visible characters and selected CJK code
    # points count individually, while unsupported scripts are tracked separately.
    word_count = (
        ascii_visible_char_count + cjk_ideograph_count + cjk_punctuation_count
    )
    non_whitespace_char_count = sum(1 for char in text if not char.isspace())
    return {
        "word_count": word_count,
        "char_count": len(text),
        "non_whitespace_char_count": non_whitespace_char_count,
        "line_count": len(lines),
        "paragraph_count": sum(1 for line in lines if line.strip()),
        "unsupported_non_whitespace_char_count": non_whitespace_char_count - word_count,
        "ascii_visible_char_count": ascii_visible_char_count,
        "cjk_ideograph_count": cjk_ideograph_count,
        "cjk_punctuation_count": cjk_punctuation_count,
    }


def _is_in_code_point_ranges(
    code_point: int, ranges: tuple[tuple[int, int], ...]
) -> bool:
    """Return whether ``code_point`` falls inside any inclusive range."""
    return any(start <= code_point <= end for start, end in ranges)
