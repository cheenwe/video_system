"""输入安全：防 SQL 注入探测、LIKE 通配符滥用、路径/控制字符等"""
from __future__ import annotations

import re
from pathlib import Path

from src.core.exceptions import BizError

LIKE_ESCAPE = "\\"
DEFAULT_KEYWORD_MAX_LEN = 100

# 常见 SQL 注入探测片段（参数化查询已防注入；用于拦截明显恶意请求）
_SQL_PROBE_RE = re.compile(
    r"(?is)"
    r"(\bunion\b.+\bselect\b)"
    r"|(\bor\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+)"
    r"|(\b(and|or)\b\s+['\"]?.+['\"]?\s*=\s*['\"]?.+['\"]?)"
    r"|(\b(drop|alter|truncate)\b\s+\b(table|database)\b)"
    r"|(\bexec\b\s*\()"
    r"|(\bxp_\w+)"
    r"|(;\s*--)"
    r"|(/\*.*\*/)"
)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control_chars(value: str) -> str:
    return _CONTROL_CHARS_RE.sub("", value)


def contains_sql_injection_probe(value: str) -> bool:
    if not value:
        return False
    return bool(_SQL_PROBE_RE.search(value))


def assert_no_sql_probe(value: str | None, *, label: str = "输入") -> None:
    if value and contains_sql_injection_probe(value):
        raise BizError(f"{label}包含非法字符", 400)


def escape_like_pattern(value: str, escape_char: str = LIKE_ESCAPE) -> str:
    esc = escape_char
    return (
        value.replace(esc, esc + esc)
        .replace("%", esc + "%")
        .replace("_", esc + "_")
    )


def normalize_search_keyword(value: str | None, max_len: int = DEFAULT_KEYWORD_MAX_LEN) -> str | None:
    if value is None:
        return None
    s = strip_control_chars(str(value).strip())
    if not s:
        return None
    if len(s) > max_len:
        s = s[:max_len]
    assert_no_sql_probe(s, label="搜索关键词")
    return s


def like_contains_pattern(
    keyword: str | None, max_len: int = DEFAULT_KEYWORD_MAX_LEN
) -> tuple[str, str] | None:
    """返回 (LIKE 模式, escape 字符)；无有效关键词时返回 None。"""
    kw = normalize_search_keyword(keyword, max_len)
    if not kw:
        return None
    return f"%{escape_like_pattern(kw)}%", LIKE_ESCAPE


def validate_upload_id(upload_id: str) -> str:
    raw = strip_control_chars((upload_id or "").strip())
    if not re.fullmatch(r"[0-9a-fA-F]{32}", raw):
        raise BizError("无效的上传任务 ID", 400)
    return raw.lower()


def sanitize_filename(filename: str) -> str:
    raw = strip_control_chars((filename or "").strip())
    if not raw or raw in {".", ".."}:
        raise BizError("文件名无效")
    if ".." in raw or "/" in raw or "\\" in raw:
        raise BizError("文件名无效")
    base = Path(raw).name
    if not base or base in {".", ".."}:
        raise BizError("文件名无效")
    if len(base) > 255:
        base = base[:255]
    assert_no_sql_probe(base, label="文件名")
    return base


def validate_token_param(token: str | None, *, max_len: int = 512) -> str:
    raw = strip_control_chars((token or "").strip())
    if not raw:
        raise BizError("缺少访问参数", 400)
    if len(raw) > max_len:
        raise BizError("访问参数无效", 400)
    assert_no_sql_probe(raw, label="访问参数")
    return raw


def validate_category_code(category: str | None, *, max_len: int = 64) -> str | None:
    if category is None:
        return None
    s = strip_control_chars(category.strip())
    if not s:
        return None
    if len(s) > max_len:
        raise BizError("分类参数过长", 400)
    if not re.fullmatch(r"[\w\-.]+", s, flags=re.ASCII):
        raise BizError("分类参数格式无效", 400)
    return s
