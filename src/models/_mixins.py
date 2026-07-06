"""ORM 公共 mixin"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

# MySQL 用 BIGINT，SQLite 自动用 INTEGER（确保自增）
PK_TYPE = BigInteger().with_variant(Integer(), "sqlite")
FK_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IdMixin:
    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
