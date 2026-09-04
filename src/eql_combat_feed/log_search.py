"""Bounded, reverse-chronological regex search for EverQuest logs."""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .watcher import _open_shared

LOG_TS_FMT = "%a %b %d %H:%M:%S %Y"
TIMESTAMP_RE = re.compile(
    rb"^\[(?P<ts>[A-Za-z]{3} [A-Za-z]{3} \d{2} \d{2}:\d{2}:\d{2} \d{4})\]"
)


@dataclass(frozen=True, slots=True)
class LogSearchResult:
    lines: tuple[str, ...]
    scanned_lines: int
    truncated: bool = False


def search_log(
    path: str | Path,
    pattern: str,
    *,
    lookback_seconds: int | None,
    exclude_pattern: str = "",
    match_case: bool = False,
    max_results: int = 500,
    now: float | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> LogSearchResult:
    """Return newest matching lines, stopping once the time range is exhausted."""
    if not pattern:
        raise ValueError("Enter a regex to search for.")
    if max_results <= 0:
        return LogSearchResult((), 0)

    flags = 0 if match_case else re.IGNORECASE
    expression = re.compile(pattern, flags)
    exclusion = re.compile(exclude_pattern, flags) if exclude_pattern else None
    cutoff = None
    if lookback_seconds is not None:
        cutoff = (datetime.now().timestamp() if now is None else now) - lookback_seconds

    matches: list[str] = []
    scanned = 0
    for raw in _iter_lines_reverse(Path(path)):
        if cancelled is not None and cancelled():
            break
        scanned += 1
        if cutoff is not None:
            timestamp = _line_timestamp(raw)
            if timestamp is not None and timestamp < cutoff:
                break
        line = raw.decode("utf-8", errors="replace")
        if expression.search(line) and (
            exclusion is None or exclusion.search(line) is None
        ):
            matches.append(line)
            if len(matches) >= max_results:
                return LogSearchResult(tuple(matches), scanned, truncated=True)
    return LogSearchResult(tuple(matches), scanned)


def _iter_lines_reverse(path: Path, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """Yield raw lines newest-first without loading the whole file."""
    with _open_shared(path, "rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        remainder = b""
        while position > 0:
            size = min(chunk_size, position)
            position -= size
            handle.seek(position)
            data = handle.read(size) + remainder
            pieces = data.split(b"\n")
            remainder = pieces[0]
            for raw in reversed(pieces[1:]):
                raw = raw.rstrip(b"\r")
                if raw:
                    yield raw
        remainder = remainder.rstrip(b"\r")
        if remainder:
            yield remainder


def _line_timestamp(raw: bytes) -> float | None:
    match = TIMESTAMP_RE.match(raw)
    if not match:
        return None
    try:
        text = match.group("ts").decode("ascii")
        return datetime.strptime(text, LOG_TS_FMT).timestamp()
    except (UnicodeDecodeError, ValueError):
        return None
