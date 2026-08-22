"""EverQuest process detection and transition tracking."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

import psutil


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
