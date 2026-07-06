"""JWT 失效令牌黑名单"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.models._mixins import PK_TYPE


class AuthRevokedToken(Base):
    __tablename__ = "auth_revoked_tokens"

    id: Mapped[int] = mapped_column(PK_TYPE, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

