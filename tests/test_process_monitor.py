from types import SimpleNamespace

from eql_combat_feed import process_monitor
from eql_combat_feed.process_monitor import (
    GameProcessEvent,
    GameProcessTracker,
    foreground_pid,
    is_game_running,
    pid_matches_process,
)


def process(name: str):
    return SimpleNamespace(info={"name": name})


def test_process_detection_is_case_insensitive_and_ignores_other_apps() -> None:
    assert is_game_running(process_iter=lambda _: [process("Discord.exe"), process("EQGAME.EXE")])
    assert not is_game_running(process_iter=lambda _: [process("notepad.exe")])


def test_tracker_does_not_report_close_before_game_has_run() -> None:
    tracker = GameProcessTracker(stop_threshold=2)

    assert tracker.observe(False) is None
    assert tracker.observe(False) is None
    assert tracker.seen_running is False


def test_tracker_debounces_stop_and_reports_each_edge_once() -> None:
    tracker = GameProcessTracker(stop_threshold=2)

    assert tracker.observe(True) is GameProcessEvent.STARTED
    assert tracker.observe(True) is None
    assert tracker.observe(False) is None
    assert tracker.running is True
    assert tracker.observe(False) is GameProcessEvent.STOPPED
    assert tracker.running is False
    assert tracker.observe(False) is None
    assert tracker.observe(True) is GameProcessEvent.STARTED


class FakeProcess:
    def __init__(self, name: str, cmdline: list[str]) -> None:
        self._name = name
        self._cmdline = cmdline

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list[str]:
        return self._cmdline


def test_macos_wine_virtual_desktop_counts_as_the_game(monkeypatch) -> None:
    table = {
        1: FakeProcess("eqgame.exe", ["C:\\...\\eqgame.exe", "patchme"]),
        2: FakeProcess(
            "explorer.exe", ["C:\\windows\\system32\\explorer.exe", "/desktop=osxEQL,1710x1072"]
        ),
        3: FakeProcess("explorer.exe", ["explorer.exe"]),
        4: FakeProcess("Google Chrome", ["/Applications/Google Chrome.app"]),
    }
    monkeypatch.setattr(process_monitor.psutil, "Process", lambda pid: table[pid])

    monkeypatch.setattr(process_monitor.sys, "platform", "darwin")
    assert pid_matches_process(1)
    assert pid_matches_process(2)
    assert not pid_matches_process(3)
    assert not pid_matches_process(4)

    monkeypatch.setattr(process_monitor.sys, "platform", "win32")
    assert not pid_matches_process(2)  # real Windows explorer is never the game


def test_foreground_pid_fails_open_without_a_gui_session(monkeypatch) -> None:
    monkeypatch.setattr(process_monitor.sys, "platform", "darwin")
    monkeypatch.setattr(process_monitor, "_macos_foreground_pid", lambda: None)
    assert foreground_pid() is None
    monkeypatch.setattr(process_monitor.sys, "platform", "linux")
    assert foreground_pid() is None
