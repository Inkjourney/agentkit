from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentkit.workspace.fs import WorkspaceFS


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def workspace_fs(workspace_root: Path) -> WorkspaceFS:
    return WorkspaceFS(workspace_root)
