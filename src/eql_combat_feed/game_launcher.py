"""Resolve and launch EverQuest from the configured log location."""

import subprocess
from collections.abc import Callable
from pathlib import Path

LAUNCHER_NAME = "LaunchPad.exe"


def launcher_from_log(log_path: str | Path | None) -> Path | None:
    """Find ``LaunchPad.exe`` beside the ``Logs`` folder containing the active log."""

    if log_path is None:
        return None
    path = Path(log_path).expanduser()
    if path.parent.name.casefold() != "logs":
        return None
    launcher = path.parent.parent / LAUNCHER_NAME
    return launcher if launcher.is_file() else None


def launch_everquest(
    log_path: str | Path | None,
    *,
    start: Callable[..., object] = subprocess.Popen,
) -> Path | None:
    """Start the official launcher and return its path, or ``None`` if unresolved."""

    launcher = launcher_from_log(log_path)
    if launcher is None:
        return None
    start([str(launcher)], cwd=str(launcher.parent))
    return launcher
