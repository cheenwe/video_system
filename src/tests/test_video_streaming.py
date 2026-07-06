from src.core.video_streaming import parse_range_header


def test_parse_range_from_start():
    assert parse_range_header("bytes=0-", 1000) == (0, 999)


def test_parse_range_suffix():
    assert parse_range_header("bytes=-500", 1000) == (500, 999)


def test_parse_range_closed():
    assert parse_range_header("bytes=100-199", 1000) == (100, 199)


def test_parse_range_invalid():
    assert parse_range_header("bytes=2000-", 1000) is None
    assert parse_range_header("invalid", 1000) is None
