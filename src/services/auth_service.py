"""认证服务"""
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.core.exceptions import BizError
from src.core.security import create_access_token, hash_password, verify_password
from src.models.user import User


def login(db: Session, username: str, password: str) -> Tuple[User, str]:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise BizError("用户名或密码错误", 401)
    if user.disabled:
        raise BizError("账号已禁用", 403)
    if not verify_password(password, user.password_hash):
        raise BizError("用户名或密码错误", 401)
    role = (user.role or "user").lower()
    token = create_access_token(
        sub=user.username,
        payload={"user_id": user.id, "username": user.username, "role": role},
    )
    return user, token


def change_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, user.password_hash):
        raise BizError("原密码错误")
    if not new_password or len(new_password) < 5:
        raise BizError("新密码至少 5 位")
    user.password_hash = hash_password(new_password)
    db.commit()
