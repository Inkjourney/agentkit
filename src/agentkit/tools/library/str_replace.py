"""str_replace tool implementation."""

from __future__ import annotations

from typing import Any

from agentkit.errors import WorkspaceError
from agentkit.tools.base import FunctionTool, Tool
from agentkit.tools.types import ToolInvocation
from agentkit.workspace.fs import WorkspaceFS

from ._fs_common import (
    error_payload,
    format_numbered_lines,
    format_path_workspace_error,
    path_details,
    read_utf8_text_for_edit,
    split_lines,
)

_SNIPPET_CONTEXT_LINES = 2


def build_str_replace_tool(fs: WorkspaceFS) -> Tool:
    """Build the workspace-bound ``str_replace`` tool."""
    return FunctionTool(
        name="str_replace",
        description=(
            "Replace a single, unique occurrence of a text string in an existing workspace file.\n"
            "\n"
            "USE THIS TOOL WHEN you need to:\n"
            "- Revise a specific passage: rephrase a paragraph, tighten wording, fix an error, "
            "adjust tone, improve clarity, etc.\n"
            "- Insert new content at a precise location by including surrounding text in `old_str` "
            "and adding the new material in `new_str`.\n"
            '- Delete a passage by replacing it with an empty string (omit `new_str` or set it to "").\n'
            "\n"
            "THIS IS THE PREFERRED TOOL for revising existing documents. "
            "Use it instead of `create_file` whenever the change is localized.\n"
            "\n"
            "BEHAVIOR:\n"
            "- Searches the file for `old_str` and replaces it with `new_str` (default: empty string).\n"
            "- The match must be EXACT (including whitespace, punctuation, and line breaks) and UNIQUE "
            "(appears exactly once in the file).\n"
            "\n"
            "IMPORTANT GUIDELINES:\n"
            "- ALWAYS `view` the relevant section of the file first to get the exact current text. "
            "Do not rely on memory — the content may have changed.\n"
            "- If the text you want to replace appears more than once, "
            "include more surrounding context in `old_str` to make it unique.\n"
            "- Ensure `new_str` reads naturally in context: maintain consistent style, voice, "
            "formatting, and terminology with the surrounding text.\n"
            "\n"
            "LIMITATIONS:\n"
            "- Only works on UTF-8 text files.\n"
            "- Exactly one occurrence of `old_str` must exist; zero or multiple matches cause an error."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A short explanation of WHAT you are changing and WHY. Be specific. "
                        "Good: 'Rephrase the opening paragraph to make the hook more compelling'. "
                        "Bad: 'edit text'."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path (from workspace root) to the file to edit. "
                        "The file must already exist and be valid UTF-8. "
                        "Example: 'draft.md', 'chapters/05.md'."
                    ),
                },
                "old_str": {
                    "type": "string",
                    "description": (
                        "The exact text to find and replace. Must appear EXACTLY ONCE in the file. "
                        "Copy this verbatim from the file content (use `view` to get it). "
                        "Include enough surrounding context to ensure uniqueness. "
                        "Whitespace, punctuation, and line breaks must match exactly."
                    ),
                },
                "new_str": {
                    "type": "string",
                    "description": (
                        "The text to replace `old_str` with. "
                        "Omit or set to empty string to DELETE the matched passage. "
                        "Ensure the replacement fits naturally into the surrounding text."
                    ),
                },
            },
            "required": ["description", "path", "old_str"],
            "additionalProperties": False,
        },
        handler=lambda args: _str_replace(fs, args),
        success_formatter=_format_str_replace_output,
        error_formatter=_format_str_replace_error,
    )


def _str_replace(fs: WorkspaceFS, args: dict[str, Any]) -> dict[str, Any]:
    """Replace one unique string occurrence and return an updated snippet."""
    path = args["path"]
    old_str = args["old_str"]
    new_str = args.get("new_str", "")
    if old_str == "":
        raise WorkspaceError("old_str must not be empty.")
    content = read_utf8_text_for_edit(fs, path)
    occurrences = content.count(old_str)
    if occurrences == 0:
        raise WorkspaceError(f"String not found in file: {old_str!r}")
    if occurrences > 1:
        raise WorkspaceError(f"String is not unique in file: {old_str!r}")
    replacement_start = content.index(old_str)
    updated_content = content.replace(old_str, new_str, 1)
    fs.write_text(path, updated_content, overwrite=True)
    snippet = _build_updated_snippet(updated_content, replacement_start, len(new_str))
    return {
        "path": path,
        "replacements": 1,
        "snippet_start_line": snippet["start_line"],
        "snippet_end_line": snippet["end_line"],
        "snippet": snippet["content"],
    }


def _format_str_replace_output(output: Any, invocation: ToolInvocation) -> Any:
    """Render the edit result with a contextual snippet when possible."""
    del invocation
    if not isinstance(output, dict):
        return output

    path = output.get("path")
    snippet = output.get("snippet")
    start_line = output.get("snippet_start_line")
    end_line = output.get("snippet_end_line")
    if not isinstance(path, str):
        return {"output": output}
    if not isinstance(snippet, str) or not snippet:
        return f"The file {path} has been edited. The file is now empty."
    return (
        f"The file {path} has been edited. "
        f"Here is a numbered snippet of the updated file around the edit "
        f"({_format_line_range(start_line, end_line)}):\n"
        f"{snippet}"
    )


def _build_updated_snippet(
    text: str, replacement_start: int, replacement_length: int
) -> dict[str, Any]:
    """Build a small numbered snippet around the replacement site."""
    lines = split_lines(text)
    if not lines:
        return {"start_line": 0, "end_line": 0, "content": ""}

    start_line = _line_number_for_offset(text, replacement_start)
    end_line = _line_number_for_offset(text, replacement_start + replacement_length)
    context_start_line = max(1, start_line - _SNIPPET_CONTEXT_LINES)
    context_end_line = min(len(lines), end_line + _SNIPPET_CONTEXT_LINES)
    snippet_lines = lines[context_start_line - 1 : context_end_line]
    return {
        "start_line": context_start_line,
        "end_line": context_end_line,
        "content": format_numbered_lines(
            snippet_lines,
            start_line=context_start_line,
            total_lines=len(lines),
        ),
    }


def _line_number_for_offset(text: str, offset: int) -> int:
    """Map a string offset back to its 1-based line number."""
    if not text:
        return 0
    bounded = max(0, min(offset, len(text)))
    if bounded == len(text) and bounded > 0:
        bounded -= 1
    return text.count("\n", 0, bounded) + 1


def _format_line_range(start_line: Any, end_line: Any) -> str:
    """Render a human-readable line range for status messages."""
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return "updated file"
    if start_line <= 0 or end_line <= 0:
        return "updated file"
    if start_line == end_line:
        return f"line {start_line}"
    return f"lines {start_line}-{end_line}"


def _format_str_replace_error(
    error: Exception, invocation: ToolInvocation
) -> dict[str, Any]:
    """Translate ``str_replace`` failures into stable model-facing errors."""
    common = format_path_workspace_error(
        error,
        invocation,
        missing_message="The file to edit does not exist in the workspace.",
        missing_hint="Call `view` first to confirm the file path, then retry `str_replace`.",
        not_file_message="str_replace only works on existing files.",
    )
    if common is not None:
        return common

    message = str(error)
    details = path_details(invocation)
    if message == "old_str must not be empty.":
        return error_payload(
            "empty_old_str",
            "old_str must not be empty.",
            hint="Copy the exact text you want to replace from the file.",
            details=details,
        )
    if message.startswith("File is not valid UTF-8 text: "):
        return error_payload(
            "non_utf8_file",
            "The target file is not valid UTF-8 text.",
            hint="Use a UTF-8 text file, or convert the file before retrying.",
            details=details,
        )
    if message.startswith("String not found in file: "):
        return error_payload(
            "string_not_found",
            "old_str was not found in the file.",
            hint="Call `view` again and copy the exact current text, including whitespace and punctuation.",
            details=details,
        )
    if message.startswith("String is not unique in file: "):
        return error_payload(
            "string_not_unique",
            "old_str matches multiple locations in the file.",
            hint="Include more surrounding context in old_str so it matches exactly one location.",
            details=details,
        )
    return error_payload("str_replace_failed", message, details=details)
