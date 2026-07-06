"""合并、校验、持久化 .env"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any

from pydantic import ValidationError

from src.core.config import RUNTIME_ROOT, Settings, get_settings
from src.core.dotenv_io import DOTENV_READONLY_KEYS, dotenv_path, parse_dotenv, serialize_dotenv
from src.core.runtime_env_docs import doc_for_key, load_full_example_env_text
from src.core.exceptions import BizError


def _value_to_dotenv(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return "" if v is None else str(v)


def load_file_dict() -> OrderedDict[str, str]:
    p = dotenv_path(RUNTIME_ROOT)
    if not p.is_file():
        return OrderedDict()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise BizError(f"无法读取 .env：{e}") from e
    return parse_dotenv(text)


def build_items() -> tuple[list[dict[str, Any]], str]:
    """返回 (items 列表 dict, 文件路径字符串)。"""
    file_map = load_file_dict()
    live = get_settings()
    fields = Settings.model_fields
    known_order = list(fields.keys())
    items: list[dict[str, Any]] = []

    for name in known_order:
        ku = name.upper()
        if ku in file_map:
            val = file_map[ku]
        else:
            val = _value_to_dotenv(getattr(live, name))
        desc, ex = doc_for_key(ku)
        items.append(
            {
                "key": ku,
                "value": val,
                "readonly": ku in DOTENV_READONLY_KEYS,
                "description": desc,
                "example": ex,
            }
        )

    known_upper = {k.upper() for k in fields}
    extras = sorted(ku for ku in file_map if ku not in known_upper)
    for ku in extras:
        desc, ex = doc_for_key(ku)
        items.append(
            {
                "key": ku,
                "value": file_map[ku],
                "readonly": False,
                "description": desc,
                "example": ex,
            }
        )

    return items, str(dotenv_path(RUNTIME_ROOT))


def full_example_env_text() -> str:
    return load_full_example_env_text()


def merge_for_write(client: dict[str, str]) -> OrderedDict[str, str]:
    """客户端提交全量键值；只读键以磁盘 .env 为准（无则取当前进程 Settings）。"""
    file_map = load_file_dict()
    live = get_settings()
    fields = Settings.model_fields
    cu = {str(k).strip().upper(): v if isinstance(v, str) else str(v) for k, v in client.items()}

    merged: OrderedDict[str, str] = OrderedDict()

    for name in fields:
        ku = name.upper()
        if ku in DOTENV_READONLY_KEYS:
            merged[ku] = file_map.get(ku) if ku in file_map else str(getattr(live, name))
            continue
        if ku in cu:
            merged[ku] = cu[ku]
        elif ku in file_map:
            merged[ku] = file_map[ku]
        else:
            merged[ku] = _value_to_dotenv(getattr(live, name))

    known_upper = {k.upper() for k in fields}
    for ku, v in file_map.items():
        if ku in known_upper:
            continue
        merged[ku] = cu.get(ku, v)

    for ku, v in cu.items():
        if ku not in merged:
            merged[ku] = v

    for rk in DOTENV_READONLY_KEYS:
        merged[rk] = file_map[rk] if rk in file_map else str(getattr(live, rk))

    return merged


def validate_known_settings(merged: OrderedDict[str, str]) -> None:
    payload: dict[str, str] = {}
    for name in Settings.model_fields:
        ku = name.upper()
        if ku not in merged:
            raise BizError(f"缺少配置项：{ku}")
        payload[name] = merged[ku]
    try:
        Settings.model_validate(payload)
    except ValidationError as e:
        err = e.errors()[0] if e.errors() else {}
        loc = err.get("loc", ())
        msg = err.get("msg", str(e))
        raise BizError(f"配置校验失败 {loc}: {msg}") from e


def write_dotenv(merged: OrderedDict[str, str]) -> None:
    validate_known_settings(merged)
    known_upper = {k.upper() for k in Settings.model_fields}
    key_order = [k.upper() for k in Settings.model_fields] + sorted(k for k in merged if k not in known_upper)
    body = serialize_dotenv(merged, key_order)
    p = dotenv_path(RUNTIME_ROOT)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".env.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(p)


def apply_client_dotenv(data: dict[str, str]) -> None:
    merged = merge_for_write(data)
    write_dotenv(merged)
    get_settings.cache_clear()
