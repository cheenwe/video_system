"""视频访问引用（加密 ID）与分享令牌"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BizError
from src.core.input_security import validate_token_param
from src.models.user import User
from src.models.video import VideoShareLink


def encode_video_ref(video_id: int) -> str:
    payload = {"typ": "vref", "vid": int(video_id)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_video_ref(token: str) -> int:
    try:
        data = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError as exc:
        raise BizError("无效的视频链接", 404) from exc
    if data.get("typ") != "vref" or not data.get("vid"):
        raise BizError("无效的视频链接", 404)
    return int(data["vid"])


def is_ref_token(token: str) -> bool:
    return "." in (token or "")


@dataclass
class VideoAccessContext:
    video_id: int
    share_link: VideoShareLink | None = None
    access_token: str | None = None

    def grants_public_play(self) -> bool:
        link = self.share_link
        if not link or not link.public_access:
            return False
        if link.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        exp = link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > now


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def try_resolve_access_token(db: Session, token: str | None) -> VideoAccessContext | None:
    """解析访问令牌；空值或旧版封面缓存参数（纯数字 v）返回 None。"""
    raw = (token or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return None
    return resolve_access_token(db, raw)


def resolve_access_token(db: Session, token: str | None) -> VideoAccessContext:
    raw = validate_token_param(token)
    if is_ref_token(raw):
        return VideoAccessContext(video_id=decode_video_ref(raw), access_token=raw)
    link = db.query(VideoShareLink).filter(VideoShareLink.token == raw).first()
    if not link:
        raise BizError("分享链接无效或已失效", 404)
    if link.public_access:
        if not link.expires_at:
            raise BizError("分享链接已失效", 403)
        now = _utc_now()
        exp = link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= now:
            raise BizError("分享链接已过期", 403)
    return VideoAccessContext(video_id=int(link.video_id), share_link=link, access_token=raw)


def create_public_share_link(
    db: Session,
    *,
    video_id: int,
    user: User,
    expires_hours: int,
) -> VideoShareLink:
    hours = int(expires_hours)
    if hours < 1 or hours > 24 * 365:
        raise BizError("有效期须在 1 小时至 365 天之间")
    expires_at = _utc_now() + timedelta(hours=hours)
    token = secrets.token_urlsafe(24)
    link = VideoShareLink(
        video_id=video_id,
        token=token,
        public_access=1,
        expires_at=expires_at.replace(tzinfo=None),
        created_by=user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def serialize_share_link(link: VideoShareLink) -> dict:
    exp = link.expires_at.isoformat(sep=" ", timespec="seconds") if link.expires_at else None
    return {
        "token": link.token,
        "public_access": bool(link.public_access),
        "expires_at": exp,
        "video_id": link.video_id,
    }
