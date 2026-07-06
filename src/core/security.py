"""认证与加密工具：密码哈希、JWT"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import bcrypt
import jwt

from src.core.config import settings


def hash_password(password: str) -> str:
    if password is None:
        password = ""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(sub: str, payload: Optional[Dict[str, Any]] = None, expires_days: Optional[int] = None) -> str:
    exp_days = expires_days if expires_days is not None else settings.JWT_EXPIRE_DAYS
    now = datetime.now(timezone.utc)
    data: Dict[str, Any] = {
        "sub": sub,
        "jti": uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=exp_days)).timestamp()),
    }
    if payload:
        data.update(payload)
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
