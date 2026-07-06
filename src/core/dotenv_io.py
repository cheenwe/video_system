"""读写运行目录下的 .env 文件（与 pydantic Settings 字段配合校验）。"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

# 仅展示、保存时强制以磁盘/进程为准（改 .env 中的 PORT 不会立即改变已启动的监听端口）
DOTENV_READONLY_KEYS: frozenset[str] = frozenset({"PORT"})


def dotenv_path(runtime_root: Path) -> Path:
    return runtime_root / ".env"


def parse_dotenv(text: str) -> OrderedDict[str, str]:
    """解析 KEY=VALUE，忽略空行与 # 整行注释；键统一为大写。"""
    out: OrderedDict[str, str] = OrderedDict()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, rest = line.partition("=")
        key = k.strip().upper()
        if not key:
            continue
        val = rest.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        else:
            # 未加引号时去掉「空格 + #」后的行内注释（与 .env.example 中写法一致）
            idx = val.find(" #")
            if idx != -1:
                val = val[:idx].rstrip()
        out[key] = val
    return out


def _escape_dotenv_value(val: str) -> str:
    if re.search(r'[\r\n="#]', val) or val.strip() != val:
        s = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    return val


def serialize_dotenv(data: OrderedDict[str, str] | dict[str, str], key_order: Iterable[str]) -> str:
    """按 key_order 输出；order 中未出现的键按字母序追加。"""
    seen: set[str] = set()
    lines: list[str] = []
    data_upper = {str(k).upper(): v for k, v in data.items()}
    for k in key_order:
        ku = str(k).upper()
        if ku not in data_upper:
            continue
        lines.append(f"{ku}={_escape_dotenv_value(data_upper[ku])}")
        seen.add(ku)
    rest = sorted(ku for ku in data_upper if ku not in seen)
    for ku in rest:
        lines.append(f"{ku}={_escape_dotenv_value(data_upper[ku])}")
    return "\n".join(lines) + ("\n" if lines else "")
