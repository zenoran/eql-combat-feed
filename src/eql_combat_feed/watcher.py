"""Discover and incrementally follow EverQuest Legends log files."""

import os
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path

DEFAULT_WINDOWS_LOG_DIR = Path(
    r"C:\Users\Public\Daybreak Game Company\Installed Games\EverQuest Legends\Logs"
)


def candidate_log_directories() -> Iterable[Path]:
    explicit = os.environ.get("EQL_LOG_DIR")
    if explicit:
        yield Path(explicit).expanduser()
    yield DEFAULT_WINDOWS_LOG_DIR
    yield Path.home() / "EverQuest Legends" / "Logs"
    yield Path.home() / "AppData" / "Local" / "EverQuest Legends" / "Logs"


def discover_log_file(explicit: str | Path | None = None) -> Path | None:
    """Find the requested log or newest ``eqlog_*.txt`` in known locations."""
    requested = explicit or os.environ.get("EQL_LOG_FILE")
    if requested:
        path = Path(requested).expanduser()
        return path if path.is_file() else None

    logs: list[Path] = []
    for directory in candidate_log_directories():
        if not directory.is_dir():
            continue
        logs.extend(path for path in directory.glob("eqlog_*.txt") if path.is_file())
    return max(logs, key=lambda path: path.stat().st_mtime, default=None)


def read_recent_lines(
    path: str | Path,
    *,
    max_lines: int = 10_000,
    max_bytes: int = 4 * 1024 * 1024,
) -> list[str]:
    """Read a bounded tail without scanning a potentially huge combat log."""
    if max_lines <= 0 or max_bytes <= 0:
        return []
    chunks: deque[bytes] = deque()
    remaining = max_bytes
    with Path(path).open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        while position > 0 and remaining > 0:
            size = min(64 * 1024, position, remaining)
            position -= size
            handle.seek(position)
            chunks.appendleft(handle.read(size))
            remaining -= size
            if b"".join(chunks).count(b"\n") > max_lines:
                break
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return text.splitlines()[-max_lines:]


class LogWatcher:
    """Non-blocking file follower designed to be polled from a Qt timer."""

    def __init__(self, path: str | Path, on_line: Callable[[str], None]) -> None:
        self.path = Path(path)
        self.on_line = on_line
        self._handle = None
        self._identity: tuple[int, int] | None = None
        self._checkpoint_offset = 0
        self._checkpoint = b""
        self._pending = ""

    def start(self, *, from_end: bool = True) -> None:
        self.close()
        self._handle = self.path.open("r", encoding="utf-8", errors="replace")
        stat = self.path.stat()
        self._identity = (stat.st_dev, stat.st_ino)
        if from_end:
            self._handle.seek(0, os.SEEK_END)
        self._capture_checkpoint()

    def poll(self) -> int:
        if self._handle is None:
            self.start()
        if self._rotated_or_truncated():
            self.start(from_end=False)

        assert self._handle is not None
        chunk = self._handle.read()
        if not chunk:
            return 0
        text = self._pending + chunk
        lines = text.splitlines(keepends=True)
        self._pending = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._pending = lines.pop()
        for raw in lines:
            self.on_line(raw.rstrip("\r\n"))
        self._capture_checkpoint()
        return len(lines)

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
        self._handle = None
        self._identity = None
        self._pending = ""

    def _rotated_or_truncated(self) -> bool:
        if self._handle is None:
            return False
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return False
        identity = (stat.st_dev, stat.st_ino)
        if identity != self._identity or stat.st_size < self._handle.tell():
            return True
        if not self._checkpoint:
            return False
        try:
            with self.path.open("rb") as probe:
                probe.seek(self._checkpoint_offset)
                current = probe.read(len(self._checkpoint))
        except OSError:
            return False
        return current != self._checkpoint

    def _capture_checkpoint(self) -> None:
        if self._handle is None:
            self._checkpoint_offset = 0
            self._checkpoint = b""
            return
        position = self._handle.tell()
        size = min(position, 64)
        self._checkpoint_offset = position - size
        try:
            with self.path.open("rb") as probe:
                probe.seek(self._checkpoint_offset)
                self._checkpoint = probe.read(size)
        except OSError:
            self._checkpoint = b""
