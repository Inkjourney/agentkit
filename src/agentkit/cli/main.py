"""CLI entrypoint for running the agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentkit.agent.agent import Agent
from agentkit.config.loader import load_config
from agentkit.errors import AgentFrameworkError


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the agent CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with global flags and the ``run``
        subcommand.
    """
    parser = argparse.ArgumentParser(
        prog="agentkit", description="LLM Agent Framework CLI"
    )
    parser.add_argument(
        "--config",
        default="examples/config.openai.yaml",
        help="Path to YAML/JSON config file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser(
        "run", help="Run one task with the configured agent."
    )
    run_parser.add_argument("--task", help="Task text to execute.")
    run_parser.add_argument("--task-file", help="Read task text from file.")
    run_parser.add_argument(
        "--report-json", help="Optional path to write run report JSON."
    )
    return parser


def main() -> None:
    """Parse arguments and dispatch to the selected CLI command.

    Returns:
        None: The process exits via normal flow or ``SystemExit``.
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        _run_command(args)


def _run_command(args: argparse.Namespace) -> None:
    """Execute the ``run`` command using the parsed CLI arguments.

    Args:
        args: Parsed command namespace from :func:`build_parser`.

    Returns:
        None: Prints the final assistant output to stdout.

    Raises:
        SystemExit: Raised with code ``2`` when agent execution fails with a framework
            error.
    """
    task = _load_task(args.task, args.task_file)
    config = load_config(args.config)
    agent = Agent.from_config(config)

    try:
        report = agent.run(task)
    except AgentFrameworkError as exc:
        print(f"[agent-error] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(report.final_output)


def _load_task(task: str | None, task_file: str | None) -> str:
    """Resolve task text from CLI flags.

    Args:
        task: Inline task text supplied via ``--task``.
        task_file: Optional path supplied via ``--task-file``.

    Returns:
        str: The task string to send to the agent.

    Raises:
        SystemExit: If neither ``task`` nor ``task_file`` is provided.
    """
    if task:
        return task
    if task_file:
        return Path(task_file).read_text(encoding="utf-8")
    raise SystemExit("Please provide --task or --task-file.")


if __name__ == "__main__":
    main()
