"""视频评论"""
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BizError
from src.models.user import User
from src.models.video import Video, VideoComment
from src.services import video_service


def _serialize_comment(c: VideoComment) -> dict:
    created = c.created_at.isoformat(sep=" ", timespec="seconds") if c.created_at else None
    return {
        "id": c.id,
        "video_id": c.video_id,
        "user_id": c.user_id,
        "display_name": c.display_name,
        "content": c.content,
        "is_anonymous": bool(c.is_anonymous),
        "created_at": created,
        "can_delete": False,
    }


def list_comments(
    db: Session,
    video_id: int,
    user: Optional[User],
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    video = video_service.get_video(db, video_id)
    if not video_service.can_view_detail(video, user):
        raise BizError("该视频为隐私内容，请登录后查看评论", 401)

    q = db.query(VideoComment).filter(VideoComment.video_id == video_id)
    total = q.count()
    guest_limit = settings.VIDEO_COMMENT_GUEST_PREVIEW
    is_guest = user is None

    if is_guest and guest_limit >= 0:
        effective_page_size = guest_limit if guest_limit > 0 else 0
        items = (
            q.order_by(VideoComment.created_at.desc(), VideoComment.id.desc())
            .limit(effective_page_size)
            .all()
        )
        return {
            "items": [_serialize_comment(c) for c in items],
            "total": total,
            "page": 1,
            "page_size": effective_page_size,
            "guest_limited": total > len(items),
            "guest_preview_limit": guest_limit,
            "login_required_for_more": is_guest and total > guest_limit,
        }

    items = (
        q.order_by(VideoComment.created_at.desc(), VideoComment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    out_items = []
    for c in items:
        row = _serialize_comment(c)
        row["can_delete"] = _can_delete_comment(c, user)
        out_items.append(row)
    return {
        "items": out_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "guest_limited": False,
        "guest_preview_limit": guest_limit,
        "login_required_for_more": False,
    }


def _can_delete_comment(comment: VideoComment, user: Optional[User]) -> bool:
    if not user:
        return False
    if (user.role or "").lower() == "admin":
        return True
    return comment.user_id is not None and comment.user_id == user.id


def create_comment(
    db: Session,
    video_id: int,
    *,
    content: str,
    anonymous: bool,
    display_name: str | None,
    user: Optional[User],
) -> VideoComment:
    video = video_service.get_video(db, video_id)
    if not video_service.can_view_detail(video, user):
        raise BizError("该视频为隐私内容，请登录后评论", 401)

    text = (content or "").strip()
    if not text:
        raise BizError("评论内容不能为空")

    use_anonymous = anonymous or user is None
    if use_anonymous:
        name = (display_name or "").strip() or "匿名用户"
        if len(name) > 32:
            raise BizError("昵称最多 32 个字符")
        uid = None
    else:
        name = (user.real_name or user.username or "用户").strip()
        uid = user.id

    comment = VideoComment(
        video_id=video_id,
        user_id=uid,
        display_name=name,
        content=text,
        is_anonymous=1 if use_anonymous else 0,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(db: Session, video_id: int, comment_id: int, user: User) -> None:
    comment = db.get(VideoComment, comment_id)
    if not comment or comment.video_id != video_id:
        raise BizError("评论不存在", 404)
    if not _can_delete_comment(comment, user):
        raise BizError("无权删除该评论", 403)
    db.delete(comment)
    db.commit()
