# Workspace API

## Overview

The workspace package provides the filesystem boundary around each agent run.
It exposes a strict root-scoped file facade plus helpers for creating the
default workspace directory layout.

## Key Classes

- `WorkspaceFS`
- `init_workspace_layout`

## API Reference

::: agentkit.workspace

::: agentkit.workspace.fs

::: agentkit.workspace.layout

## Notes

`WorkspaceFS.resolve_path(...)` accepts absolute or workspace-relative paths,
but always rejects paths that escape the configured workspace root.

`WorkspaceFS` also provides JSON helpers (`read_json` and `write_json`) on top
of the text read/write methods.
