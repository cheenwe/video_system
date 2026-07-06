"""CSV 导入通用小工具（UTF-8 BOM 由接口层处理）"""
from __future__ import annotations

from typing import Any, Dict


def norm_row(row: Dict[Any, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in row.items():
        if k is None:
            continue
        key = str(k).strip().lower()
        out[key] = "" if v is None else str(v).strip()
    return out


def parse_int(val: str | None, default: int = 0) -> int:
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(float(str(val).strip()))
    except (TypeError, ValueError):
        return default


def parse_float(val: str | None) -> float | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).strip())
    except (TypeError, ValueError):
        return None


def parse_disabled(val: str | None) -> int:
    s = (val or "").strip().lower()
    if s in ("1", "true", "yes", "y", "是", "禁用", "disabled"):
        return 1
    return 0
