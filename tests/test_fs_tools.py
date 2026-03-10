from __future__ import annotations

from agentkit.tools.library.fs_tools import build_tools
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.types import ToolCallOutcome, ToolInvocation
from agentkit.workspace.fs import WorkspaceFS


def _execute(
    registry: ToolRegistry,
    name: str,
    arguments: dict[str, object],
) -> ToolCallOutcome:
    return registry.execute(ToolInvocation(name=name, arguments=arguments))


def test_fs_tools_execute_end_to_end(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))

    create_result = _execute(
        registry,
        "create_file",
        {
            "description": "Create a todo file",
            "path": "notes/todo.txt",
            "file_text": "buy milk\ncall mom",
        },
    )
    assert create_result.is_error is False
    assert create_result.output == {
        "path": "notes/todo.txt",
        "chars_written": 17,
        "line_count": 2,
        "word_count": 14,
        "size_bytes": 17,
        "operation": "created",
        "previous_file": None,
    }
    assert create_result.model_payload == "File created: notes/todo.txt (2 lines, 17B, 14 words)"

    view_file_result = _execute(
        registry,
        "view",
        {"description": "Inspect file", "path": "notes/todo.txt"},
    )
    assert view_file_result.is_error is False
    assert view_file_result.output == {
        "path": "notes/todo.txt",
        "kind": "file",
        "start_line": 1,
        "end_line": 2,
        "total_lines": 2,
        "size_bytes": 17,
        "encoding": "utf-8",
        "lines": ["buy milk", "call mom"],
        "content": "1: buy milk\n2: call mom",
    }
    assert (
        view_file_result.model_payload
        == "File: notes/todo.txt (2 lines, 17B)\n---\n1: buy milk\n2: call mom\n---"
    )

    replace_result = _execute(
        registry,
        "str_replace",
        {
            "description": "Replace one item",
            "path": "notes/todo.txt",
            "old_str": "milk",
            "new_str": "coffee",
        },
    )
    assert replace_result.is_error is False
    assert replace_result.output == {
        "path": "notes/todo.txt",
        "replacements": 1,
        "snippet_start_line": 1,
        "snippet_end_line": 2,
        "snippet": "1: buy coffee\n2: call mom",
    }
    assert (
        replace_result.model_payload
        == "The file notes/todo.txt has been edited. "
        "Here is a numbered snippet of the updated file around the edit "
        "(lines 1-2):\n"
        "1: buy coffee\n2: call mom"
    )

    post_replace_view_result = _execute(
        registry,
        "view",
        {"description": "Re-read updated file", "path": "notes/todo.txt"},
    )
    assert post_replace_view_result.is_error is False
    assert post_replace_view_result.output["content"] == replace_result.output["snippet"]

    view_dir_result = _execute(
        registry,
        "view",
        {"description": "Inspect directory", "path": "notes"},
    )
    assert view_dir_result.is_error is False
    assert view_dir_result.output == {
        "path": "notes",
        "kind": "directory",
        "entries": [{"path": "todo.txt", "kind": "file", "depth": 1}],
        "directory_count": 0,
        "file_count": 1,
    }
    assert (
        view_dir_result.model_payload
        == "Directory: notes/ (0 subdirectories, 1 file)\n---\nnotes/\n└── todo.txt\n---"
    )
    assert workspace_fs.read_text("notes/todo.txt") == "buy coffee\ncall mom"


def test_create_file_overwrites_existing_file(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))

    first = _execute(
        registry,
        "create_file",
        {
            "description": "Create file",
            "path": "file.txt",
            "file_text": "v1",
        },
    )
    second = _execute(
        registry,
        "create_file",
        {
            "description": "Overwrite file",
            "path": "file.txt",
            "file_text": "v2",
        },
    )

    assert first.is_error is False
    assert second.is_error is False
    assert first.model_payload == "File created: file.txt (1 line, 2B, 2 words)"
    assert second.output == {
        "path": "file.txt",
        "chars_written": 2,
        "line_count": 1,
        "word_count": 2,
        "size_bytes": 2,
        "operation": "overwritten",
        "previous_file": {"line_count": 1, "size_bytes": 2},
    }
    assert (
        second.model_payload
        == "File overwritten: file.txt (1 line, 2B, 2 words)\n"
        "Note: Previous file (1 line, 2B) was replaced."
    )
    assert workspace_fs.read_text("file.txt") == "v2"


def test_view_directory_filters_hidden_and_limits_depth(
    workspace_fs: WorkspaceFS,
) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))

    workspace_fs.write_text("tree/visible.txt", "visible")
    workspace_fs.write_text("tree/.hidden.txt", "hidden")
    workspace_fs.write_text("tree/node_modules/pkg/index.js", "ignored")
    workspace_fs.write_text("tree/sub/child.txt", "child")
    workspace_fs.write_text("tree/sub/.secret.txt", "secret")
    workspace_fs.write_text("tree/sub/deeper/grand.txt", "grand")
    workspace_fs.write_text("tree/sub/deeper/level3/too_deep.txt", "too deep")

    result = _execute(
        registry,
        "view",
        {"description": "Inspect directory tree", "path": "tree"},
    )

    assert result.is_error is False
    assert result.output["entries"] == [
        {"path": "sub", "kind": "directory", "depth": 1},
        {"path": "sub/child.txt", "kind": "file", "depth": 2},
        {"path": "sub/deeper", "kind": "directory", "depth": 2},
        {"path": "visible.txt", "kind": "file", "depth": 1},
    ]
    assert (
        result.model_payload
        == "Directory: tree/ (2 subdirectories, 2 files)\n---\n"
        "tree/\n"
        "├── sub/\n"
        "│   ├── child.txt\n"
        "│   └── deeper/\n"
        "└── visible.txt\n"
        "---"
    )


def test_view_file_ranges_and_validation(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.write_text("lines.txt", "alpha\nbeta\ngamma")

    clipped = _execute(
        registry,
        "view",
        {
            "description": "Read tail of file",
            "path": "lines.txt",
            "view_range": [2, 99],
        },
    )
    assert clipped.is_error is False
    assert clipped.output["start_line"] == 2
    assert clipped.output["end_line"] == 3
    assert clipped.output["content"] == "2: beta\n3: gamma"
    assert (
        clipped.model_payload
        == "File: lines.txt | Lines 2-3 (of 3)\n---\n2: beta\n3: gamma\n---"
    )

    invalid_shape = _execute(
        registry,
        "view",
        {
            "description": "Bad range",
            "path": "lines.txt",
            "view_range": [2],
        },
    )
    assert invalid_shape.is_error is True
    assert "two-item array" in (invalid_shape.error or "")

    beyond_eof = _execute(
        registry,
        "view",
        {
            "description": "Range past EOF",
            "path": "lines.txt",
            "view_range": [4, -1],
        },
    )
    assert beyond_eof.is_error is True
    assert "beyond the end of file" in (beyond_eof.error or "")

    reversed_range = _execute(
        registry,
        "view",
        {
            "description": "Reversed range",
            "path": "lines.txt",
            "view_range": [3, 2],
        },
    )
    assert reversed_range.is_error is True
    assert "must be -1 or >= start_line" in (reversed_range.error or "")


def test_view_non_utf8_file_uses_backslashreplace(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.resolve_path("encoded.txt").write_bytes(b"ok\xff\nend")

    result = _execute(
        registry,
        "view",
        {"description": "Inspect non-utf8 file", "path": "encoded.txt"},
    )

    assert result.is_error is False
    assert result.output["encoding"] == "utf-8/backslashreplace"
    assert result.output["content"] == "1: ok\\xff\n2: end"
    assert (
        result.model_payload
        == "File: encoded.txt (2 lines, 7B)\n---\n1: ok\\xff\n2: end\n---"
    )


def test_str_replace_requires_unique_match(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.write_text("text.txt", "alpha beta alpha")

    missing = _execute(
        registry,
        "str_replace",
        {
            "description": "Missing target",
            "path": "text.txt",
            "old_str": "gamma",
        },
    )
    duplicate = _execute(
        registry,
        "str_replace",
        {
            "description": "Duplicate target",
            "path": "text.txt",
            "old_str": "alpha",
        },
    )

    assert missing.is_error is True
    assert "String not found" in (missing.error or "")
    assert duplicate.is_error is True
    assert "not unique" in (duplicate.error or "")


def test_word_count_reports_platform_character_metrics(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.write_text("mixed.txt", "你好 world\n\n再见 agent")

    result = _execute(
        registry,
        "word_count",
        {"description": "Count mixed text", "path": "mixed.txt"},
    )

    assert result.is_error is False
    assert result.output == {
        "path": "mixed.txt",
        "word_count": 14,
        "char_count": 18,
        "non_whitespace_char_count": 14,
        "line_count": 3,
        "paragraph_count": 2,
        "unsupported_non_whitespace_char_count": 0,
        "ascii_visible_char_count": 10,
        "cjk_ideograph_count": 4,
        "cjk_punctuation_count": 0,
    }
    assert result.model_payload == "The file mixed.txt has 14 words across 3 lines."


def test_word_count_excludes_unsupported_scripts_and_symbols(
    workspace_fs: WorkspaceFS,
) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.write_text("platform.txt", "A你，！　ａ０éあア한😀𠀀･\nZ【】!")

    result = _execute(
        registry,
        "word_count",
        {"description": "Count platform-style characters", "path": "platform.txt"},
    )

    assert result.is_error is False
    assert result.output == {
        "path": "platform.txt",
        "word_count": 9,
        "char_count": 19,
        "non_whitespace_char_count": 17,
        "line_count": 2,
        "paragraph_count": 2,
        "unsupported_non_whitespace_char_count": 8,
        "ascii_visible_char_count": 3,
        "cjk_ideograph_count": 2,
        "cjk_punctuation_count": 4,
    }
    assert result.model_payload == "The file platform.txt has 9 words across 2 lines."


def test_view_truncates_large_file_in_model_payload(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    file_text = "\n".join(f"line {index}" for index in range(1, 301))
    workspace_fs.write_text("big.txt", file_text)

    result = _execute(
        registry,
        "view",
        {"description": "Inspect large file", "path": "big.txt"},
    )

    assert result.is_error is False
    assert "File: big.txt (300 lines" in result.model_payload
    assert "  1: line 1" in result.model_payload
    assert "250: line 250" in result.model_payload
    assert "251: line 251" not in result.model_payload
    assert (
        "(Showing lines 1-250 of 300. Use view with view_range to see more.)"
        in result.model_payload
    )


def test_word_count_rejects_binary_files(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.resolve_path("blob.bin").write_bytes(b"\x00\x01\x02\x03")

    result = _execute(
        registry,
        "word_count",
        {"description": "Count binary file", "path": "blob.bin"},
    )

    assert result.is_error is True
    assert "Binary file" in (result.error or "")
    assert result.model_payload == {
        "error": {
            "code": "binary_file",
            "message": "word_count only works on text files, not binary files.",
            "hint": "Choose a text file such as .md, .txt, or another UTF-8 document.",
            "details": {"path": "blob.bin"},
        }
    }


def test_word_count_rejects_non_utf8_text(workspace_fs: WorkspaceFS) -> None:
    registry = ToolRegistry()
    registry.register_many(build_tools(workspace_fs))
    workspace_fs.resolve_path("encoded.txt").write_bytes(b"ok\xff\nend")

    result = _execute(
        registry,
        "word_count",
        {"description": "Count non-utf8 text", "path": "encoded.txt"},
    )

    assert result.is_error is True
    assert result.error == "File is not valid UTF-8 text: encoded.txt"
    assert result.model_payload == {
        "error": {
            "code": "invalid_text_encoding",
            "message": "word_count requires valid UTF-8 text for exact counting.",
            "hint": "Convert the file to UTF-8 and retry.",
            "details": {"path": "encoded.txt"},
        }
    }
