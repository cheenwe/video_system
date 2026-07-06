"""用户头像存储"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import UploadFile

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BizError
from src.models.user import User

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


def _avatars_dir() -> Path:
    p = settings.user_avatars_root_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def avatar_abs_path(user: User) -> Path | None:
    if not user.avatar_path:
        return None
    p = settings.resolve_upload_file(user.avatar_path)
    return p if p.is_file() else None


def avatar_url(user: User) -> str | None:
    path = avatar_abs_path(user)
    if not path:
        return None
    return f"/api/auth/avatars/{user.id}?v={path.stat().st_mtime_ns}"


def avatar_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "image/jpeg"


async def save_avatar(db: Session, user: User, file: UploadFile) -> User:
    original = (file.filename or "").strip()
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise BizError("仅支持 PNG / JPG / GIF / WEBP 头像")
    data = await file.read()
    if not data:
        raise BizError("文件为空")
    if len(data) > MAX_AVATAR_BYTES:
        raise BizError("头像文件过大，最大 2MB")

    save_name = f"{user.id}{ext}"
    dest = _avatars_dir() / save_name
    for old in _avatars_dir().glob(f"{user.id}.*"):
        if old.name != save_name:
            try:
                old.unlink()
            except OSError:
                pass
    dest.write_bytes(data)

    rel = str(dest.relative_to(settings.upload_root_path)).replace("\\", "/")
    user.avatar_path = rel
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def remove_avatar(db: Session, user: User) -> User:
    if user.avatar_path:
        try:
            path = settings.resolve_upload_file(user.avatar_path)
        except BizError:
            path = None
        if path and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    user.avatar_path = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
