# Custom Tools

A custom tool is a small Python function that AgentKit can call during a run.

This guide shows a beginner-friendly workflow:

1. create a tool file inside your own project
2. point `tools.entries` at that file
3. allow the tool in `tools.allowed`
4. create the agent with `create_agent(...)`
5. run a normal task

You do not need to edit AgentKit's built-in tool package to add your own tools.

## What You Will Build

In this example, you will add a custom tool named `generate_password`.

That tool will:

- generate a random password
- let the caller choose the password length
- optionally include special characters

The agent will then use the built-in `create_file` tool to save the generated
password to a file inside the workspace.

## Example Project

```text
my-project/
├─ agentkit.yaml
├─ run_agent.py
└─ tools/
   └─ password_tools.py
```

## Step 1: Create The Tool File

Create `tools/password_tools.py`:

```python
from __future__ import annotations

import secrets
import string
from typing import Any

from agentkit.tools import FunctionTool, ToolModelError


def build_password(args: dict[str, Any]) -> dict[str, Any]:
    """Generate a password from simple user-provided rules."""
    length = args["length"]
    include_special = args["include_special"]

    if length < 8:
        raise ToolModelError(
            code="length_too_short",
            message="Password length must be at least 8 characters.",
            hint="Use a length of 8 or more.",
        )

    if length > 128:
        raise ToolModelError(
            code="length_too_long",
            message="Password length must be 128 characters or fewer.",
            hint="Use a shorter password length.",
        )

    alphabet = string.ascii_letters + string.digits
    if include_special:
        alphabet += "!@#$%^&*()-_=+[]{}:,.?"

    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return {
        "password": password,
        "length": length,
        "include_special": include_special,
    }


def format_success(output: dict[str, Any], _invocation: Any) -> str:
    """Return a short result the agent can use in the next step."""
    special_text = "with" if output["include_special"] else "without"
    return (
        f"Generated a {output['length']}-character password {special_text} special characters.\n"
        f"Password: {output['password']}"
    )


def format_error(error: Exception, _invocation: Any) -> dict[str, Any]:
    """Return a clear error message if the tool fails."""
    if isinstance(error, ToolModelError):
        return error.to_model_payload()
    return {
        "error": {
            "code": "password_generation_failed",
            "message": "The password generator could not create a password.",
            "hint": "Retry with a valid length and a boolean include_special value.",
        }
    }


TOOLS = [
    FunctionTool(
        name="generate_password",
        description=(
            "Generate a random password from caller-provided rules.\n"
            "\n"
            "USE THIS TOOL WHEN you need to:\n"
            "- Create a new password for an account, environment, or credential file.\n"
            "- Produce a password that follows explicit rules such as minimum length or whether "
            "special characters should be included.\n"
            "- Hand the generated password to another tool step, such as saving it with `create_file`.\n"
            "\n"
            "BEHAVIOR:\n"
            "- Generates one random password using Python's `secrets` module.\n"
            "- Always includes letters and digits.\n"
            "- Adds special characters only when `include_special` is `true`.\n"
            "- Returns both the generated password and the rule settings that were used.\n"
            "\n"
            "IMPORTANT GUIDELINES:\n"
            "- Use this tool only when the user has clearly asked for a generated password or secret.\n"
            "- If the password will be saved to disk, choose a clear workspace path and explain what the "
            "file contains.\n"
            "- Do not invent extra password rules beyond the provided arguments.\n"
            "\n"
            "LIMITATIONS:\n"
            "- Password length must be between 8 and 128 characters.\n"
            "- This tool generates a password but does not store it by itself."
        ),
        parameters={
            "type": "object",
            "properties": {
                "length": {
                    "type": "integer",
                    "description": (
                        "Required. Total password length to generate. "
                        "Must be an integer between 8 and 128. "
                        "Use a larger value for stronger passwords. "
                        "Example: `20` generates a 20-character password."
                    ),
                },
                "include_special": {
                    "type": "boolean",
                    "description": (
                        "Required. Whether to include special characters such as `!`, `@`, `#`, or `?` "
                        "in addition to letters and digits. "
                        "Use `true` when the password should include symbols; use `false` when a simpler "
                        "alphanumeric password is required."
                    ),
                },
            },
            "required": ["length", "include_special"],
            "additionalProperties": False,
        },
        handler=build_password,
        success_formatter=format_success,
        error_formatter=format_error,
    )
]
```

### What Each Part Does

- `FunctionTool(...)` defines one tool the agent can call.
- `name` is the tool name you will later list in `tools.allowed`.
- `parameters` describe the input the tool expects.
- `handler` contains the real logic.
- `success_formatter` turns the result into a short message the agent can use right away.
- `error_formatter` returns a clear error payload if something goes wrong.

For most users, `TOOLS = [...]` is the simplest way to define custom tools.

Keep the parameter schema simple. The supported fields are:

- `type`
- `properties`
- `required`
- `additionalProperties`

## Step 2: Add The Tool To Your Config

Create `agentkit.yaml`:

```yaml
workspace:
  root: ./workspace

provider:
  kind: openai
  model: gpt-5-mini
  openai_api_variant: responses
  api_key_env: OPENAI_API_KEY

agent:
  system_prompt: You are a careful assistant. Use tools when helpful.
  budget:
    max_steps: 10
    time_budget_s: 120
    max_input_chars: 20000

tools:
  entries:
    - ./tools/password_tools.py
  allowed:
    - generate_password
    - create_file

runlog:
  enabled: true
  redact: true
  max_text_chars: 20000
```

### Why Both Lists Matter

- `tools.entries` tells AgentKit where to load custom tools from.
- `tools.allowed` tells AgentKit which discovered tools the agent may actually use.

In this example:

- `generate_password` is your custom tool
- `create_file` is a built-in tool that writes the result to a file

Relative `tools.entries` paths are resolved from the config file location.

## Step 3: Run The Agent

Create `run_agent.py`:

```python
from agentkit import create_agent

agent = create_agent("agentkit.yaml")

report = agent.run(
    "Generate a 20-character password with special characters for a new staging account. "
    "Save it to secrets/staging_admin_password.txt with a short note explaining what it is, "
    "then tell me where you saved it."
)

print(report.final_output)
```

This is the normal package workflow:

```python
from agentkit import create_agent

agent = create_agent("agentkit.yaml")
report = agent.run("...")
```

## What The Agent Does

With the files above in place, a typical run works like this:

1. AgentKit loads the built-in tools and your `tools/password_tools.py` file.
2. The agent sees only the tools listed in `tools.allowed`.
3. The agent calls `generate_password` to create the password.
4. The agent calls `create_file` to save it to `secrets/staging_admin_password.txt`.
5. The agent returns a final answer telling you where it saved the file.

The file will be created inside your configured workspace root, so the full path
will be under `./workspace/secrets/staging_admin_password.txt`.

## Optional: Load A Whole Tools Directory

If you want to keep several custom tools in one folder, point `tools.entries` at
the directory instead of one file:

```yaml
tools:
  entries:
    - ./tools
  allowed:
    - generate_password
    - create_file
```

When you use a directory:

- AgentKit loads `__init__.py` first when present
- AgentKit discovers direct child `.py` files in sorted order
- files whose names start with `_` are ignored during discovery

That makes it easy to keep helper code in files such as `_shared.py`.

## Common Pitfalls

- Forgetting to add your custom tool name to `tools.allowed`
- Pointing `tools.entries` at a file or directory that does not define any tools
- Using a tool name that contains `.`
- Returning raw exceptions when a clearer `ToolModelError` message would be easier for the agent to recover from
- Expecting full JSON Schema support beyond the small supported subset shown above

## Related

- [Agent From Config](./agent-from-config.md)
- [Configuration](../getting-started/configuration.md)
