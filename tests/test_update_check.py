from eql_combat_feed.update_check import is_newer, parse_version


def test_parse_version_handles_tags_and_plain() -> None:
    assert parse_version("v0.14.0") == (0, 14, 0)
    assert parse_version("0.13.2") == (0, 13, 2)
    assert parse_version("1.2.3-rc1") == (1, 2, 3)
    assert parse_version("nightly") is None
    assert parse_version("") is None


def test_is_newer_compares_numerically_not_lexically() -> None:
    assert is_newer("v0.14.0", "0.13.2")
    assert is_newer("v0.13.10", "0.13.9")  # 10 > 9 despite lexical order
    assert not is_newer("v0.13.2", "0.13.2")
    assert not is_newer("v0.13.1", "0.13.2")
    assert not is_newer("garbage", "0.13.2")
    assert not is_newer("v1.0.0", "garbage")
