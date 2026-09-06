"""Resolve and launch EverQuest from the configured log location."""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

LAUNCHER_NAME = "LaunchPad.exe"
# osxEQL (Wine + DXMT) owns the game on macOS; its menu-bar app is the supported
# way in. Running LaunchPad.exe as a native process is meaningless there, and
# re-creating osxEQL's Wine environment by hand is how prefixes get corrupted.
MACOS_OSXEQL_APP = Path("/Applications/osxEQL.app")


def launcher_from_log(log_path: str | Path | None) -> Path | None:
    """Find the launcher for the install whose ``Logs`` folder holds the active log.

    Windows: ``LaunchPad.exe`` beside ``Logs``. macOS: the osxEQL app bundle,
    but only when the log actually lives inside an osxEQL Wine prefix.
    """

    if log_path is None:
        return None
    path = Path(log_path).expanduser()
    if path.parent.name.casefold() != "logs":
        return None
    if sys.platform == "darwin":
        return _macos_launcher(path)
    launcher = path.parent.parent / LAUNCHER_NAME
    return launcher if launcher.is_file() else None


def _macos_launcher(log: Path) -> Path | None:
    inside_osxeql = any(parent.name == "osxEQL" for parent in log.parents)
    if inside_osxeql and MACOS_OSXEQL_APP.is_dir():
        return MACOS_OSXEQL_APP
    return None


def launch_everquest(
    log_path: str | Path | None,
    *,
    start: Callable[..., object] = subprocess.Popen,
) -> Path | None:
    """Start the official launcher and return its path, or ``None`` if unresolved."""

    launcher = launcher_from_log(log_path)
    if launcher is None:
        return None
    if launcher.suffix == ".app":
        start(["/usr/bin/open", "-a", str(launcher)], cwd=str(Path.home()))
    else:
        start([str(launcher)], cwd=str(launcher.parent))
    return launcher
