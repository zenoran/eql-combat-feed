import os
import sys
from pathlib import Path

import pytest

from eql_combat_feed import watcher as watcher_module
from eql_combat_feed.watcher import LogWatcher, discover_log_file, read_recent_lines


def test_explicit_log_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("", encoding="utf-8")
    assert discover_log_file(log) == log

    monkeypatch.setattr(watcher_module, "candidate_log_directories", lambda: ())
    assert discover_log_file(tmp_path / "missing.txt") is None


def test_recent_lines_reads_only_requested_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    class BoundedFile:
        def __init__(self) -> None:
            self.position = 0
            self.seek_calls = []
            self.read_sizes = []
            self.data = b"ancient\n" * 100_000 + b"recent one\nrecent two\n"

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def seek(self, offset: int, whence: int = 0) -> None:
            self.seek_calls.append((offset, whence))
            if whence == 2:
                self.position = len(self.data) + offset
            elif whence == 1:
                self.position += offset
            else:
                self.position = offset

        def tell(self) -> int:
            return self.position

        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            if size < 0:
                size = len(self.data) - self.position
            value = self.data[self.position : self.position + size]
            self.position += len(value)
            return value

    fake = BoundedFile()
    # Patch the opener seam, not Path.open — on Windows _open_shared goes
    # through CreateFileW and never touches Path.open.
    monkeypatch.setattr(watcher_module, "_open_shared", lambda path, mode="r": fake)
    lines = read_recent_lines("ignored", max_lines=2, max_bytes=64 * 1024)

    assert lines == ["recent one", "recent two"]
    assert fake.read_sizes == [64 * 1024]
    assert sum(fake.read_sizes) <= 64 * 1024


def test_watcher_follows_complete_appended_lines(tmp_path: Path) -> None:
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("old line\n", encoding="utf-8")
    seen = []
    watcher = LogWatcher(log, seen.append)
    watcher.start(from_end=True)

    with log.open("a", encoding="utf-8") as handle:
        handle.write("new one\npartial")
    assert watcher.poll() == 1
    assert seen == ["new one"]

    with log.open("a", encoding="utf-8") as handle:
        handle.write(" line\n")
    assert watcher.poll() == 1
    assert seen == ["new one", "partial line"]
    watcher.close()


def test_watcher_reopens_after_truncation(tmp_path: Path) -> None:
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("old line\n", encoding="utf-8")
    seen = []
    watcher = LogWatcher(log, seen.append)
    watcher.start(from_end=True)

    log.write_text("replacement\n", encoding="utf-8")
    watcher.poll()
    assert seen == ["replacement"]
    watcher.close()


def test_restart_replays_only_a_bounded_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replaced multi-GB log must never be slurped whole; only a tail replays."""
    log = tmp_path / "eqlog_Hero_freeport.txt"
    lines = [f"line {index:04d}" for index in range(200)]  # 10 bytes per line
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setattr(watcher_module, "MAX_REPLAY_BYTES", 105)
    seen: list[str] = []
    watcher = LogWatcher(log, seen.append)
    watcher.start(from_end=False)
    watcher.poll()
    watcher.close()

    assert seen  # the tail was delivered...
    assert len(seen) < 20  # ...but nowhere near the whole file
    assert seen[-1] == "line 0199"
    # The line straddling the cut point was dropped, not delivered mangled.
    assert all(line in lines for line in seen)


def test_small_file_restart_still_replays_everything(tmp_path: Path) -> None:
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("first\nsecond\n", encoding="utf-8")
    seen: list[str] = []
    watcher = LogWatcher(log, seen.append)
    watcher.start(from_end=False)
    watcher.poll()
    watcher.close()
    assert seen == ["first", "second"]


@pytest.mark.skipif(sys.platform != "win32", reason="FILE_SHARE_DELETE only matters on Windows")
def test_watched_log_stays_deletable_on_windows(tmp_path: Path) -> None:
    """Log-trimming tools must be able to delete the log while the overlay runs."""
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("old line\n", encoding="utf-8")
    watcher = LogWatcher(log, lambda line: None)
    watcher.start(from_end=True)
    try:
        os.remove(log)
    finally:
        watcher.close()
    assert not log.exists()


def test_stale_requested_log_falls_back_to_directory_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved-but-missing log path must not blind discovery permanently."""
    real = tmp_path / "eqlog_Hero_freeport.txt"
    real.write_text("", encoding="utf-8")
    monkeypatch.setenv("EQL_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("EQL_LOG_FILE", raising=False)
    assert discover_log_file(tmp_path / "eqlog_Gone_missing.txt") == real
