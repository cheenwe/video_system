"""用户模型 - 复用项目原 users 表语义"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models._mixins import PK_TYPE


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    disabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    real_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
