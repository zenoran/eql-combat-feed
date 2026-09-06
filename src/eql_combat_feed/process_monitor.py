"""EverQuest process detection and transition tracking."""

import logging
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

import psutil

LOG = logging.getLogger(__name__)


class GameProcessEvent(StrEnum):
    STARTED = "started"
    STOPPED = "stopped"


@dataclass(slots=True)
class GameProcessTracker:
    """Report debounced start/stop edges without nagging before the game has run."""

    stop_threshold: int = 2
    seen_running: bool = False
    running: bool = False
    _missing_observations: int = 0

    def observe(self, running: bool) -> GameProcessEvent | None:
        if running:
            event = GameProcessEvent.STARTED if not self.running else None
            self.seen_running = True
            self.running = True
            self._missing_observations = 0
            return event
        if not self.running:
            self._missing_observations = 0
            return None
        self._missing_observations += 1
        if self._missing_observations < self.stop_threshold:
            return None
        self.running = False
        self._missing_observations = 0
        return GameProcessEvent.STOPPED


def is_game_running(
    process_names: Iterable[str] = ("eqgame.exe",),
    process_iter: Callable[..., Iterable[object]] = psutil.process_iter,
) -> bool:
    """Return whether any configured EverQuest executable is currently running."""

    expected = {name.casefold() for name in process_names}
    try:
        processes = process_iter(["name"])
        for process in processes:
            try:
                info = getattr(process, "info", {})
                name = info.get("name") if isinstance(info, dict) else None
                if name and str(name).casefold() in expected:
                    return True
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
    except (psutil.AccessDenied, psutil.Error):
        return False
    return False


def foreground_pid() -> int | None:
    """PID of the process owning the foreground window, or ``None`` if unknown.

    ``None`` means "cannot tell", which callers treat as focused (fail open):
    a wrong guess hides the feed mid-fight, an unknown just leaves it visible.
    """
    if sys.platform == "win32":
        return _windows_foreground_pid()
    if sys.platform == "darwin":
        return _macos_foreground_pid()
    return None


def _windows_foreground_pid() -> int | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def _macos_foreground_pid() -> int | None:
    # NSWorkspace only answers inside a GUI login session (a bundled .app or a
    # terminal on the desktop); from SSH it returns None, which fails open.
    try:
        from AppKit import NSWorkspace  # type: ignore[import-not-found]
    except ImportError:
        _warn_once("AppKit unavailable; overlays stay visible regardless of focus")
        return None
    try:
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception as error:  # noqa: BLE001 — any AppKit hiccup is "unknown", not "hidden"
        _warn_once(f"NSWorkspace lookup failed ({error!r}); overlays stay visible")
        return None
    if front is None:
        _warn_once("NSWorkspace reports no frontmost application; overlays stay visible")
        return None
    return int(front.processIdentifier()) or None


_warned: set[str] = set()


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        LOG.warning(message)


def pid_matches_process(
    pid: int, process_names: Iterable[str] = ("eqgame.exe",)
) -> bool:
    """Whether ``pid`` belongs to one of the named executables.

    On macOS the game runs inside a Wine virtual desktop owned by Wine's own
    ``explorer.exe /desktop=...``; focusing that desktop window counts as the
    game being focused too.
    """
    expected = {name.casefold() for name in process_names}
    try:
        process = psutil.Process(pid)
        name = process.name().casefold()
        if name in expected:
            return True
        if sys.platform == "darwin" and name == "explorer.exe":
            return any(arg.casefold().startswith("/desktop=") for arg in process.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
        return False
    return False
