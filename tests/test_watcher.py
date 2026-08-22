from pathlib import Path

from eql_combat_feed.watcher import LogWatcher, discover_log_file, read_recent_lines


def test_explicit_log_discovery(tmp_path: Path) -> None:
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("", encoding="utf-8")
    assert discover_log_file(log) == log
    assert discover_log_file(tmp_path / "missing.txt") is None


def test_recent_lines_reads_only_requested_tail() -> None:
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
    original_open = Path.open
    Path.open = lambda self, *args, **kwargs: fake  # type: ignore[method-assign]
    try:
        lines = read_recent_lines("ignored", max_lines=2, max_bytes=64 * 1024)
    finally:
        Path.open = original_open  # type: ignore[method-assign]

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
