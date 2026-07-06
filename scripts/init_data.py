"""初始化数据库与基础种子数据。

用法（在项目根目录执行）：
  python scripts/init_data.py

若仍遇找不到 src，可显式指定 PYTHONPATH：
  PYTHONPATH=. python scripts/init_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 直接运行本脚本时，解释器默认不把项目根加入 sys.path；必须在 import src 之前处理
_ROOT = Path(__file__).resolve().parent.parent
_ROOT_S = str(_ROOT)
if _ROOT_S not in sys.path:
    sys.path.insert(0, _ROOT_S)

from src.core.init_db import init_database


def main() -> None:
    init_database()
    print("init done")


if __name__ == "__main__":
    main()
