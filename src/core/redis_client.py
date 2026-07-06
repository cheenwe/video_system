"""可选 Redis 连接（未配置 REDIS_URL 时不启用）。"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from src.core.config import settings

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_redis_client() -> Any | None:
    if not settings.redis_enabled:
        return None
    import redis

    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def ping_redis() -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:
        logger.debug("Redis ping failed", exc_info=True)
        return False


def close_redis() -> None:
    client = get_redis_client()
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    get_redis_client.cache_clear()
