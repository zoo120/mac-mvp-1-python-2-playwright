"""Runtime configuration shared by local and server deployments."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def env_path(name: str, default: str | Path) -> Path:
    """Read a filesystem path from an environment variable."""
    value = os.getenv(name)
    if not value:
        return Path(default)
    return Path(value).expanduser()


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def browser_headless() -> bool:
    """Whether Playwright should run without a visible browser window."""
    return env_flag("XIANYU_HEADLESS", False)


def browser_args() -> list[str]:
    """Extra Chromium flags for server/container environments."""
    if env_flag("XIANYU_NO_SANDBOX", False):
        return ["--no-sandbox"]
    return []
