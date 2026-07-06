"""系统配置"""
from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models._mixins import FK_TYPE, IdMixin, TimestampMixin


class SysConfig(IdMixin, TimestampMixin, Base):
    __tablename__ = "sys_configs"
    __table_args__ = (UniqueConstraint("category", "code", name="uq_sysconfig_cat_code"),)

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(FK_TYPE, nullable=True)
