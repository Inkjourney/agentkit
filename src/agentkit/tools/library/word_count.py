"""word_count tool implementation."""

from __future__ import annotations

from typing import Any

from agentkit.errors import WorkspaceError
from agentkit.tools.base import FunctionTool, Tool
from agentkit.tools.types import ToolInvocation
from agentkit.workspace.fs import WorkspaceFS

from ._fs_common import (
    count_text_metrics,
    error_payload,
    format_count,
    format_path_workspace_error,
    is_probably_binary,
    path_details,
    resolve_existing_file,
)


def build_word_count_tool(fs: WorkspaceFS) -> Tool:
    """Build the workspace-bound ``word_count`` tool."""
    return FunctionTool(
        name="word_count",
        description=(
            "Count the number of words and lines in a workspace text file.\n"
            "\n"
            "USE THIS TOOL WHEN you need to:\n"
            "- Verify whether a draft meets a minimum or maximum word count.\n"
            "- Report text metrics after writing or revising.\n"
            "\n"
            "RETURNS:\n"
            "- `word_count`: number of words.\n"
            "- `line_count`: the total number of lines in the file.\n"
            "\n"
            "LIMITATIONS:\n"
            "- Only works on text files in the workspace. Binary files are rejected.\n"
            "- The file must be valid UTF-8."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A short explanation of WHY you need the word count. Be specific. "
                        "Good: 'Verify the revised draft meets the 3,000-word target'. "
                        "Bad: 'count words'."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path (from workspace root) to the text file to count. "
                        "Must be an existing text file (not a directory, not a binary file). "
                        "Example: 'draft.md', 'report.md'."
                    ),
                },
            },
            "required": ["description", "path"],
            "additionalProperties": False,
        },
        handler=lambda args: _word_count(fs, args),
        success_formatter=_format_word_count_output,
        error_formatter=_format_word_count_error,
    )


def _word_count(fs: WorkspaceFS, args: dict[str, Any]) -> dict[str, Any]:
    """Count text metrics for an existing UTF-8 workspace file."""
    path = args["path"]
    target = resolve_existing_file(fs, path)
    data = target.read_bytes()
    if is_probably_binary(data):
        raise WorkspaceError(f"Binary file is not supported for word_count: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError(f"File is not valid UTF-8 text: {path}") from exc
    return {
        "path": path,
        **count_text_metrics(text),
    }


def _format_word_count_output(output: Any, invocation: ToolInvocation) -> Any:
    """Render the human-facing count summary shown back to the model."""
    del invocation
    if not isinstance(output, dict):
        return output
    path = output.get("path")
    word_count = output.get("word_count")
    line_count = output.get("line_count")
    if (
        isinstance(path, str)
        and isinstance(word_count, int)
        and isinstance(line_count, int)
    ):
        return (
            f"The file {path} has {format_count(word_count, 'word')} "
            f"across {format_count(line_count, 'line')}."
        )
    return {"output": output}


def _format_word_count_error(
    error: Exception, invocation: ToolInvocation
) -> dict[str, Any]:
    """Translate ``word_count`` failures into stable model-facing errors."""
    common = format_path_workspace_error(
        error,
        invocation,
        missing_message="The file to count does not exist in the workspace.",
        missing_hint="Choose an existing text file path inside the workspace.",
        not_file_message="word_count only works on files.",
    )
    if common is not None:
        return common

    message = str(error)
    details = path_details(invocation)
    if message.startswith("Binary file is not supported for word_count: "):
        return error_payload(
            "binary_file",
            "word_count only works on text files, not binary files.",
            hint="Choose a text file such as .md, .txt, or another UTF-8 document.",
            details=details,
        )
    if message.startswith("File is not valid UTF-8 text: "):
        return error_payload(
            "invalid_text_encoding",
            "word_count requires valid UTF-8 text for exact counting.",
            hint="Convert the file to UTF-8 and retry.",
            details=details,
        )
    return error_payload("word_count_failed", message, details=details)
