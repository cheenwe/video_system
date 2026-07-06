"""日志配置"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # 降噪
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.WARNING)


logger = logging.getLogger("lab_system")
