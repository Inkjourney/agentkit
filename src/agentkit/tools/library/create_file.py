"""create_file tool implementation."""

from __future__ import annotations

from typing import Any

from agentkit.tools.base import FunctionTool, Tool
from agentkit.tools.types import ToolInvocation
from agentkit.workspace.fs import WorkspaceFS

from ._fs_common import (
    count_text_metrics,
    error_payload,
    format_count,
    format_human_size,
    format_path_workspace_error,
    path_details,
)


def build_create_file_tool(fs: WorkspaceFS) -> Tool:
    """Build the workspace-bound ``create_file`` tool."""
    return FunctionTool(
        name="create_file",
        description=(
            "Create a new file or completely overwrite an existing file with the provided text content.\n"
            "\n"
            "USE THIS TOOL WHEN you need to:\n"
            "- Create a brand-new document: a draft, outline, translation, summary, report, etc.\n"
            "- Completely rewrite an existing file when the changes are so extensive that making "
            "individual edits with `str_replace` would be impractical.\n"
            "\n"
            "BEHAVIOR:\n"
            "- Writes the exact content of `file_text` as UTF-8. Parent directories are created automatically.\n"
            "- If the file already exists, it is FULLY OVERWRITTEN — all previous content is lost.\n"
            "- Returns file metrics after writing, including line count and platform word count.\n"
            "\n"
            "IMPORTANT GUIDELINES:\n"
            "- PREFER `str_replace` over this tool when only a localized revision is needed. "
            "Overwriting an entire document to change a few sentences risks introducing unintended changes.\n"
            "- The content in `file_text` must be COMPLETE and ready to use. "
            "Do not leave placeholders like '[TODO]' or '[continue here]' unless the user explicitly asks for them.\n"
            "\n"
            "LIMITATIONS:\n"
            "- Only UTF-8 text is supported.\n"
            "- The path must resolve to a location inside the workspace."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "A short explanation of WHY you are creating or overwriting this file. Be specific. "
                        "Good: 'Create the first draft of the project proposal based on the outline'. "
                        "Bad: 'create file'."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path (from workspace root) for the file to create or overwrite. "
                        "Parent directories will be created if they don't exist. "
                        "Examples: 'chapters/03.md', 'report-v2.md'."
                    ),
                },
                "file_text": {
                    "type": "string",
                    "description": (
                        "The COMPLETE text content to write into the file. "
                        "This must be the full desired file content — not a partial fragment or a diff. "
                        "Include proper formatting, paragraph breaks, and structure as appropriate."
                    ),
                },
            },
            "required": ["description", "path", "file_text"],
            "additionalProperties": False,
        },
        handler=lambda args: _create_file(fs, args),
        success_formatter=_format_create_file_output,
        error_formatter=_format_create_file_error,
    )


def _create_file(fs: WorkspaceFS, args: dict[str, Any]) -> dict[str, Any]:
    """Create or overwrite a text file and return post-write metrics."""
    path = args["path"]
    file_text = args["file_text"]
    target = fs.resolve_path(path)
    previous_meta: dict[str, Any] | None = None
    # Preserve the previous file size/line count so the model can see that an
    # overwrite replaced existing content rather than creating a new file.
    if target.exists() and target.is_file():
        previous_bytes = target.read_bytes()
        previous_meta = {
            "line_count": len(previous_bytes.splitlines()) if previous_bytes else 0,
            "size_bytes": len(previous_bytes),
        }
    fs.write_text(path, file_text, overwrite=True)
    size_bytes = len(file_text.encode("utf-8"))
    metrics = count_text_metrics(file_text)
    return {
        "path": path,
        "chars_written": len(file_text),
        "line_count": metrics["line_count"],
        "word_count": metrics["word_count"],
        "size_bytes": size_bytes,
        "operation": "overwritten" if previous_meta is not None else "created",
        "previous_file": previous_meta,
    }


def _format_create_file_output(output: Any, invocation: ToolInvocation) -> Any:
    """Render a concise summary of the create or overwrite operation."""
    del invocation
    if not isinstance(output, dict):
        return output

    path = output.get("path")
    line_count = output.get("line_count")
    size_bytes = output.get("size_bytes")
    word_count = output.get("word_count")
    operation = output.get("operation")
    previous_file = output.get("previous_file")
    if not (
        isinstance(path, str)
        and isinstance(line_count, int)
        and isinstance(size_bytes, int)
        and isinstance(word_count, int)
        and operation in {"created", "overwritten"}
    ):
        return {"output": output}

    prefix = "File created" if operation == "created" else "File overwritten"
    message = (
        f"{prefix}: {path} "
        f"({format_count(line_count, 'line')}, {format_human_size(size_bytes)}, "
        f"{format_count(word_count, 'word')})"
    )
    if operation == "overwritten" and isinstance(previous_file, dict):
        previous_line_count = previous_file.get("line_count")
        previous_size_bytes = previous_file.get("size_bytes")
        if isinstance(previous_line_count, int) and isinstance(
            previous_size_bytes, int
        ):
            message += (
                "\n"
                f"Note: Previous file ({format_count(previous_line_count, 'line')}, "
                f"{format_human_size(previous_size_bytes)}) was replaced."
            )
    return message


def _format_create_file_error(
    error: Exception, invocation: ToolInvocation
) -> dict[str, Any]:
    """Translate ``create_file`` failures into stable model-facing errors."""
    common = format_path_workspace_error(
        error,
        invocation,
        missing_message="The target path could not be prepared inside the workspace.",
        missing_hint="Choose a writable path inside the workspace.",
    )
    if common is not None:
        return common
    return error_payload(
        "create_file_failed", str(error), details=path_details(invocation)
    )
