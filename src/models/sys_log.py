"""系统日志（最小集合：谁、何时、IP、做了什么）"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models._mixins import FK_TYPE, PK_TYPE


class SysLog(Base):
    __tablename__ = "sys_logs"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_id: Mapped[int | None] = mapped_column(FK_TYPE, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tag: Mapped[str] = mapped_column(String(32), nullable=False, default="operation")  # login | operation | audit
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="success")  # success | failed
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
