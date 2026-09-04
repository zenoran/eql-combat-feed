from datetime import datetime

import pytest

from eql_combat_feed.log_search import _iter_lines_reverse, search_log


def timestamp(text: str) -> float:
    return datetime.strptime(text, "%a %b %d %H:%M:%S %Y").timestamp()


def test_reverse_reader_handles_lf_crlf_and_missing_final_newline(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_bytes(b"first\r\nsecond\nthird")

    assert list(_iter_lines_reverse(path, chunk_size=4)) == [b"third", b"second", b"first"]


def test_reverse_reader_handles_lines_crossing_chunk_boundaries(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    long_line = b"middle-" + b"x" * 80_000
    path.write_bytes(b"oldest\n" + long_line + b"\nnewest\n")

    assert list(_iter_lines_reverse(path)) == [b"newest", long_line, b"oldest"]


def test_search_returns_newest_matches_and_stops_at_lookback(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text(
        "[Sat Aug 22 09:00:00 2026] ancient goblin\n"
        "[Sat Aug 22 10:00:00 2026] recent orc\n"
        "[Sat Aug 22 10:30:00 2026] recent goblin\n",
        encoding="utf-8",
    )

    result = search_log(
        path,
        "goblin|orc",
        lookback_seconds=60 * 60,
        now=timestamp("Sat Aug 22 10:45:00 2026"),
    )

    assert result.lines == (
        "[Sat Aug 22 10:30:00 2026] recent goblin",
        "[Sat Aug 22 10:00:00 2026] recent orc",
    )
    assert result.scanned_lines == 3
    assert result.truncated is False


def test_search_case_sensitivity_and_python_regex(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text("[Sat Aug 22 10:00:00 2026] Goblin hits for 42\n", encoding="utf-8")

    insensitive = search_log(path, r"goblin hits for \d+", lookback_seconds=None)
    sensitive = search_log(
        path,
        r"goblin hits for \d+",
        lookback_seconds=None,
        match_case=True,
    )

    assert len(insensitive.lines) == 1
    assert sensitive.lines == ()


def test_search_excludes_matching_lines_with_same_case_rules(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text(
        "[Sat Aug 22 10:00:00 2026] Goblin hits YOU\n"
        "[Sat Aug 22 10:01:00 2026] Goblin hits your pet\n"
        "[Sat Aug 22 10:02:00 2026] Orc hits YOU\n",
        encoding="utf-8",
    )

    result = search_log(
        path,
        "goblin",
        exclude_pattern="PET",
        lookback_seconds=None,
    )

    assert result.lines == ("[Sat Aug 22 10:00:00 2026] Goblin hits YOU",)


def test_invalid_exclude_regex_is_rejected(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text("anything\n", encoding="utf-8")

    with pytest.raises(Exception) as error:
        search_log(path, ".", exclude_pattern="(", lookback_seconds=None)
    assert "unterminated" in str(error.value).lower()


def test_search_limits_results_and_reports_truncation(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text("\n".join(f"line {number}" for number in range(5)), encoding="utf-8")

    result = search_log(path, "line", lookback_seconds=None, max_results=2)

    assert result.lines == ("line 4", "line 3")
    assert result.scanned_lines == 2
    assert result.truncated is True


def test_search_can_be_cancelled(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text("old\nnew\n", encoding="utf-8")

    result = search_log(path, ".", lookback_seconds=None, cancelled=lambda: True)

    assert result.lines == ()
    assert result.scanned_lines == 0


def test_search_rejects_empty_and_invalid_regex(tmp_path) -> None:
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text("anything\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Enter a regex"):
        search_log(path, "", lookback_seconds=None)
    with pytest.raises(Exception) as error:
        search_log(path, "(", lookback_seconds=None)
    assert "unterminated" in str(error.value).lower()
