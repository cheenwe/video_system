"""用户服务"""
from __future__ import annotations

import csv
from io import StringIO
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.core.exceptions import BizError
from src.core.input_security import like_contains_pattern
from src.core.security import hash_password
from src.models.user import User
from src.schemas.user import UserCreate, UserSelfProfileUpdate, UserUpdate
from src.services.csv_helpers import norm_row, parse_disabled


def list_users(db: Session, page: int, page_size: int, keyword: Optional[str]) -> Tuple[List[User], int]:
    q = db.query(User)
    like_info = like_contains_pattern(keyword)
    if like_info:
        like, esc = like_info
        q = q.filter(User.username.ilike(like, escape=esc))
    total = q.count()
    items = q.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def create_user(db: Session, data: UserCreate) -> User:
    if db.query(User).filter(User.username == data.username).first():
        raise BizError("用户名已存在")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        real_name=data.real_name,
        disabled=0,
        timezone=data.timezone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, uid: int, data: UserUpdate) -> User:
    user = db.get(User, uid)
    if not user:
        raise BizError("用户不存在", 404)
    if data.username and data.username != user.username:
        if db.query(User).filter(User.username == data.username, User.id != uid).first():
            raise BizError("用户名已存在")
        user.username = data.username
    if data.role:
        user.role = data.role
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.new_password:
        user.password_hash = hash_password(data.new_password)
    if data.timezone is not None:
        user.timezone = data.timezone
    db.commit()
    db.refresh(user)
    return user


def update_self_profile(db: Session, user: User, data: UserSelfProfileUpdate) -> User:
    payload = data.model_dump(exclude_unset=True)
    if "real_name" in payload:
        user.real_name = (payload.get("real_name") or "").strip() or None
    if "timezone" in payload:
        user.timezone = payload["timezone"]
    db.commit()
    db.refresh(user)
    return user


def set_disabled(db: Session, uid: int, disabled: bool) -> User:
    user = db.get(User, uid)
    if not user:
        raise BizError("用户不存在", 404)
    user.disabled = 1 if disabled else 0
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, uid: int, current_uid: int) -> None:
    if uid == current_uid:
        raise BizError("不能删除自己")
    user = db.get(User, uid)
    if not user:
        raise BizError("用户不存在", 404)
    db.delete(user)
    db.commit()


def reset_password(db: Session, uid: int, new_password: str) -> User:
    user = db.get(User, uid)
    if not user:
        raise BizError("用户不存在", 404)
    if not new_password or len(new_password) < 5:
        raise BizError("新密码至少 5 位")
    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


_USER_EXPORT_HEADER = ["username", "role", "disabled", "real_name", "timezone"]


def export_users_csv(db: Session) -> str:
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(_USER_EXPORT_HEADER)
    for u in db.query(User).order_by(User.id.asc()).all():
        w.writerow([u.username, u.role or "user", u.disabled, u.real_name or "", u.timezone or "UTC"])
    return buf.getvalue()


def import_users_from_csv(db: Session, text: str) -> dict[str, int]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise BizError("CSV 无表头")
    created = 0
    updated = 0
    line_no = 1
    for raw in reader:
        line_no += 1
        row = norm_row(raw)
        username = (row.get("username") or "").strip()
        if not username:
            continue
        role = (row.get("role") or "user").strip() or "user"
        if role not in ("admin", "user"):
            raise BizError(f"第 {line_no} 行：role 须为 admin 或 user")
        disabled = parse_disabled(row.get("disabled"))
        real_name = (row.get("real_name") or "").strip() or None
        timezone = (row.get("timezone") or "UTC").strip() or "UTC"
        password = (row.get("password") or "").strip()
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            update_user(
                db,
                existing.id,
                UserUpdate(
                    role=role,
                    real_name=real_name,
                    timezone=timezone,
                ),
            )
            set_disabled(db, existing.id, bool(disabled))
            if password:
                reset_password(db, existing.id, password)
            updated += 1
        else:
            if len(password) < 5:
                raise BizError(f"第 {line_no} 行：新建用户须填写 password（至少 5 位）")
            u_new = create_user(
                db,
                UserCreate(
                    username=username,
                    password=password,
                    role=role,
                    real_name=real_name,
                    timezone=timezone,
                ),
            )
            if disabled:
                set_disabled(db, u_new.id, True)
            created += 1
    return {"created": created, "updated": updated}
