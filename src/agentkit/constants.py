"""Project-level constants."""

from __future__ import annotations

from pathlib import Path

DEFAULT_WORKSPACE_DIRS: tuple[str, ...] = ("logs",)
DEFAULT_RUNLOG_PATH = Path("logs/run.jsonl")
DEFAULT_ENCODING = "utf-8"

DEFAULT_MAX_STEPS = 20
DEFAULT_TIME_BUDGET_S = 300
DEFAULT_MAX_INPUT_CHARS = 20_000

SENSITIVE_KEYS: tuple[str, ...] = (
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "refresh_token",
    "secret",
)
