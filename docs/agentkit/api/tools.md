# Tools API

## Overview

The `tools` package defines the tool interface, runtime registry, dynamic tool
loading, and the built-in filesystem tool library.

## Key Classes

- `Tool` and `FunctionTool`
- `ToolRegistry`
- `ToolInvocation`
- `ToolCallOutcome`
- `ToolModelError`
- `load_tools_from_entries`

## API Reference

::: agentkit.tools

::: agentkit.tools.base

::: agentkit.tools.types

::: agentkit.tools.registry

::: agentkit.tools.loader

::: agentkit.tools.library.fs_tools

::: agentkit.tools.library.view

::: agentkit.tools.library.create_file

::: agentkit.tools.library.str_replace

::: agentkit.tools.library.word_count

## Notes

`ToolRegistry.execute` accepts `ToolInvocation`, performs JSON-schema-like
argument validation, and returns `ToolCallOutcome`.

`load_tools_from_library(...)` loads built-in modules from
`agentkit.tools.library`; `load_tools_from_entries(...)` loads user-defined tool
modules from configured file or directory paths.

Tool success payloads are formatter-defined. Some tools return structured
dictionaries to the model, while others return plain text strings when a narrated
result is more useful.
