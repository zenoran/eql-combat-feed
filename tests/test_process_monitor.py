from types import SimpleNamespace

from eql_combat_feed.process_monitor import (
    GameProcessEvent,
    GameProcessTracker,
    is_game_running,
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
