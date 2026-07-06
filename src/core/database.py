"""数据库引擎与会话工厂"""
from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.core.config import RUNTIME_ROOT, settings


def _normalize_sqlite_url(url: str) -> str:
    """相对路径 SQLite 固定到运行根目录（打包后 exe 旁），避免受当前工作目录影响。"""
    if not url.startswith("sqlite"):
        return url
    rest = url.removeprefix("sqlite:///")
    if not rest:
        return url
    if rest.startswith("//"):
        return url
    if rest.startswith("/") or (len(rest) > 1 and rest[1] == ":"):
        return url
    p = Path(rest)
    if not p.is_absolute():
        p = (RUNTIME_ROOT / p).resolve()
    return "sqlite:///" + p.as_posix()


def _create_engine():
    url = _normalize_sqlite_url(settings.DATABASE_URL)
    kwargs = {
        "pool_pre_ping": True,
        "future": True,
    }
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_recycle"] = 3600
    return create_engine(url, **kwargs)


engine = _create_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    """SQLAlchemy 声明基类"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
