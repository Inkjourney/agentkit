"""Workspace filesystem facade with strict path isolation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentkit.errors import WorkspaceError


class WorkspaceFS:
    """Read/write operations scoped to a single workspace root."""

    def __init__(self, root: str | Path) -> None:
        """Create a workspace filesystem facade and ensure root exists.

        Args:
            root: Workspace root directory.

        Returns:
            None
        """
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, path: str | Path) -> Path:
        """Resolve a path and enforce workspace containment.

        Args:
            path: Absolute or workspace-relative path.

        Returns:
            pathlib.Path: Fully resolved path within the workspace root.

        Raises:
            agentkit.errors.WorkspaceError: If the resolved path escapes workspace
                boundaries.
        """
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.expanduser().resolve(strict=False)

        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceError(f"Path escapes workspace: {path}")
        return resolved

    def exists(self, path: str | Path) -> bool:
        """Check whether a path exists inside the workspace.

        Args:
            path: Absolute or workspace-relative path.

        Returns:
            bool: ``True`` when the resolved path exists.

        Raises:
            agentkit.errors.WorkspaceError: If the path escapes workspace boundaries.
        """
        return self.resolve_path(path).exists()

    def is_file(self, path: str | Path) -> bool:
        """Check whether a path points to a file inside the workspace.

        Args:
            path: Absolute or workspace-relative path.

        Returns:
            bool: ``True`` when the resolved path exists and is a file.

        Raises:
            agentkit.errors.WorkspaceError: If the path escapes workspace boundaries.
        """
        return self.resolve_path(path).is_file()

    def is_dir(self, path: str | Path) -> bool:
        """Check whether a path points to a directory inside the workspace.

        Args:
            path: Absolute or workspace-relative path.

        Returns:
            bool: ``True`` when the resolved path exists and is a directory.

        Raises:
            agentkit.errors.WorkspaceError: If the path escapes workspace boundaries.
        """
        return self.resolve_path(path).is_dir()

    def mkdir(
        self, path: str | Path, *, parents: bool = True, exist_ok: bool = True
    ) -> Path:
        """Create a directory inside the workspace.

        Args:
            path: Absolute or workspace-relative directory path.
            parents: Whether to create missing parent directories.
            exist_ok: Whether existing directory is allowed.

        Returns:
            pathlib.Path: Resolved directory path.

        Raises:
            agentkit.errors.WorkspaceError: If the path escapes workspace boundaries.
            FileExistsError: If target exists and ``exist_ok`` is ``False``.
        """
        target = self.resolve_path(path)
        target.mkdir(parents=parents, exist_ok=exist_ok)
        return target

    def list_dir(self, path: str | Path = ".") -> list[str]:
        """List entries in a workspace directory.

        Args:
            path: Absolute or workspace-relative directory path.

        Returns:
            list[str]: Sorted entry names.

        Raises:
            agentkit.errors.WorkspaceError: If path is outside workspace, missing, or
                not a directory.
        """
        target = self.resolve_path(path)
        if not target.exists():
            raise WorkspaceError(f"Directory does not exist: {path}")
        if not target.is_dir():
            raise WorkspaceError(f"Not a directory: {path}")
        return sorted(entry.name for entry in target.iterdir())

    def read_text(self, path: str | Path, *, encoding: str = "utf-8") -> str:
        """Read UTF-8 text from a workspace file.

        Args:
            path: Absolute or workspace-relative file path.
            encoding: Text encoding used for reading.

        Returns:
            str: File content.

        Raises:
            agentkit.errors.WorkspaceError: If path is outside workspace, missing, or
                not a file.
        """
        target = self.resolve_path(path)
        if not target.exists():
            raise WorkspaceError(f"File does not exist: {path}")
        if not target.is_file():
            raise WorkspaceError(f"Not a file: {path}")
        return target.read_text(encoding=encoding)

    def write_text(
        self,
        path: str | Path,
        text: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
    ) -> None:
        """Write text to a workspace file.

        Args:
            path: Absolute or workspace-relative file path.
            text: Text content to persist.
            encoding: Text encoding used for writing.
            overwrite: Whether existing files may be replaced.

        Returns:
            None

        Raises:
            agentkit.errors.WorkspaceError: If path escapes workspace or overwrite is
                disallowed for an existing file.
        """
        target = self.resolve_path(path)
        if target.exists() and not overwrite:
            raise WorkspaceError(f"File already exists and overwrite=False: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding=encoding)

    def append_text(
        self, path: str | Path, text: str, *, encoding: str = "utf-8"
    ) -> None:
        """Append text to a workspace file, creating it if needed.

        Args:
            path: Absolute or workspace-relative file path.
            text: Text content to append.
            encoding: Text encoding used for writing.

        Returns:
            None

        Raises:
            agentkit.errors.WorkspaceError: If path escapes workspace boundaries.
        """
        target = self.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding=encoding) as f:
            f.write(text)

    def edit_text(
        self,
        path: str | Path,
        old: str,
        new: str,
        *,
        count: int | None = None,
        encoding: str = "utf-8",
    ) -> int:
        """Replace text occurrences in a workspace file.

        Args:
            path: Absolute or workspace-relative file path.
            old: Substring to replace.
            new: Replacement substring.
            count: Optional maximum number of replacements.
            encoding: Text encoding used for read/write operations.

        Returns:
            int: Number of replacements applied.

        Raises:
            agentkit.errors.WorkspaceError: If ``old`` is empty, ``count`` is
                negative, or the path is invalid.
        """
        if old == "":
            raise WorkspaceError("edit_text 'old' pattern must not be empty.")

        content = self.read_text(path, encoding=encoding)
        occurrences = content.count(old)
        if occurrences == 0:
            return 0

        if count is None:
            updated = content.replace(old, new)
            replaced = occurrences
        else:
            if count < 0:
                raise WorkspaceError("edit_text 'count' must be >= 0 when provided.")
            updated = content.replace(old, new, count)
            replaced = min(occurrences, count)

        self.write_text(path, updated, encoding=encoding, overwrite=True)
        return replaced

    def read_json(self, path: str | Path) -> Any:
        """Read and decode JSON from a workspace file.

        Args:
            path: Absolute or workspace-relative JSON file path.

        Returns:
            Any: Decoded JSON payload.

        Raises:
            agentkit.errors.WorkspaceError: If the path is invalid.
            json.JSONDecodeError: If file content is not valid JSON.
        """
        return json.loads(self.read_text(path))

    def write_json(
        self,
        path: str | Path,
        data: Any,
        *,
        ensure_ascii: bool = False,
        indent: int = 2,
    ) -> None:
        """Encode and write JSON to a workspace file.

        Args:
            path: Absolute or workspace-relative destination path.
            data: JSON-serializable payload.
            ensure_ascii: Whether to escape non-ASCII characters.
            indent: Pretty-print indentation size.

        Returns:
            None

        Raises:
            agentkit.errors.WorkspaceError: If path is invalid.
            TypeError: If ``data`` contains non-serializable values.
        """
        self.write_text(
            path, json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
        )
