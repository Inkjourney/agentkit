# CLI Usage

## Prerequisites

- AgentKit installed in the environment
- A config file path available via `--config`

## Step 1

Show CLI help.

```bash
uv run agentkit --help
```

## Step 2

Run with inline task.

```bash
uv run agentkit --config agentkit.quickstart.yaml run --task "List files in workspace"
```

## Step 3

Run with a task file instead of inline text.

```bash
uv run agentkit --config agentkit.quickstart.yaml run \
  --task-file ./task.txt
```

## Step 4

Persist run report JSON.

```bash
uv run agentkit --config agentkit.quickstart.yaml run \
  --task "Create notes/cli.txt with one line" \
  --report-json ./report.json
```

## Full Example

```bash
export OPENAI_API_KEY="your-key"

uv run agentkit --config agentkit.quickstart.yaml run \
  --task "Create notes/meeting.txt and write a summary" \
  --report-json ./report.json
```

## Expected Output

- Final assistant output printed to stdout
- Optional JSON file written from `RunReport.to_dict()` when `--report-json` is provided

## Exit Behavior

- Missing both `--task` and `--task-file` raises `SystemExit`
- Framework runtime failures are printed to stderr as `[agent-error] ...`
- Framework runtime failures exit with status code `2`

## Common Pitfalls

- Omitting both `--task` and `--task-file` (CLI exits with an error)
- Passing an unreadable `--task-file`
- Missing API key required by provider config

## Related

- [Quickstart](../getting-started/quickstart.md)
- [Agent Lifecycle](../concepts/agent-lifecycle.md)
