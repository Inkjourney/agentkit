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

Tool success payloads are formatter-defined. Some tools return structured
dictionaries to the model, while others return plain text strings when a narrated
result is more useful.
