from src.core.config import Settings


def test_redis_enabled_when_url_set():
    s = Settings(REDIS_URL="redis://localhost:6379/0")
    assert s.redis_enabled is True


def test_redis_disabled_when_url_empty():
    s = Settings(REDIS_URL="")
    assert s.redis_enabled is False
