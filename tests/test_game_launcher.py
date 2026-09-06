from pathlib import Path

from eql_combat_feed.game_launcher import launch_everquest, launcher_from_log


def make_install(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "EverQuest Legends"
    logs = root / "Logs"
    logs.mkdir(parents=True)
    log = logs / "eqlog_Hero_freeport.txt"
    log.write_text("", encoding="utf-8")
    launcher = root / "LaunchPad.exe"
    launcher.write_bytes(b"")
    return log, launcher


def test_launcher_is_resolved_from_logs_parent(tmp_path: Path) -> None:
    log, launcher = make_install(tmp_path)

    assert launcher_from_log(log) == launcher


def test_launcher_resolution_rejects_unrelated_or_incomplete_paths(tmp_path: Path) -> None:
    unrelated = tmp_path / "eqlog_Hero_freeport.txt"
    unrelated.write_text("", encoding="utf-8")
    missing_launcher = tmp_path / "EverQuest Legends" / "Logs" / "eqlog_Hero_freeport.txt"
    missing_launcher.parent.mkdir(parents=True)
    missing_launcher.write_text("", encoding="utf-8")

    assert launcher_from_log(None) is None
    assert launcher_from_log(unrelated) is None
    assert launcher_from_log(missing_launcher) is None


def test_launch_everquest_uses_launcher_directory_as_working_directory(tmp_path: Path) -> None:
    log, launcher = make_install(tmp_path)
    calls: list[tuple[list[str], str]] = []

    launched = launch_everquest(
        log,
        start=lambda command, cwd: calls.append((command, cwd)),
    )

    assert launched == launcher
    assert calls == [([str(launcher)], str(launcher.parent))]
