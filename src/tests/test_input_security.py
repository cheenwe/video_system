import pytest

from src.core.exceptions import BizError
from src.core.input_security import (
    contains_sql_injection_probe,
    escape_like_pattern,
    like_contains_pattern,
    normalize_search_keyword,
    sanitize_filename,
    validate_upload_id,
)


def test_escape_like_pattern():
    assert escape_like_pattern("100%_off") == "100\\%\\_off"


def test_like_contains_pattern():
    info = like_contains_pattern("hello")
    assert info is not None
    pattern, esc = info
    assert pattern == "%hello%"
    assert esc == "\\"


def test_sql_probe_blocks_union():
    with pytest.raises(BizError):
        normalize_search_keyword("foo' UNION SELECT 1")


def test_validate_upload_id():
    assert validate_upload_id("a" * 32) == "a" * 32
    with pytest.raises(BizError):
        validate_upload_id("not-hex")


def test_sanitize_filename_rejects_path():
    with pytest.raises(BizError):
        sanitize_filename("../../etc/passwd")
    assert sanitize_filename("clip.mp4") == "clip.mp4"


def test_contains_sql_probe():
    assert contains_sql_injection_probe("1 OR 1=1")
    assert not contains_sql_injection_probe("正常搜索")
