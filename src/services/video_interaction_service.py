"""视频点赞与收藏"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.core.exceptions import BizError
from src.models.user import User
from src.models.video import Video, VideoFavorite, VideoLike
from src.services import video_service


def user_flags(db: Session, video_id: int, user_id: Optional[int]) -> dict:
    if not user_id:
        return {"liked": False, "favorited": False}
    liked = (
        db.query(VideoLike.id)
        .filter(VideoLike.video_id == video_id, VideoLike.user_id == user_id)
        .first()
        is not None
    )
    favorited = (
        db.query(VideoFavorite.id)
        .filter(VideoFavorite.video_id == video_id, VideoFavorite.user_id == user_id)
        .first()
        is not None
    )
    return {"liked": liked, "favorited": favorited}


def interaction_state(db: Session, video: Video, user: Optional[User]) -> dict:
    flags = user_flags(db, video.id, user.id if user else None)
    return {
        "like_count": video.like_count or 0,
        "favorite_count": video.favorite_count or 0,
        **flags,
    }


def toggle_like(db: Session, video_id: int, user: User) -> dict:
    video = video_service.get_video(db, video_id)
    if not video_service.can_view_detail(video, user):
        raise BizError("无权操作该视频", 403)
    row = (
        db.query(VideoLike)
        .filter(VideoLike.video_id == video_id, VideoLike.user_id == user.id)
        .first()
    )
    if row:
        db.delete(row)
        video.like_count = max((video.like_count or 0) - 1, 0)
        liked = False
    else:
        db.add(VideoLike(video_id=video_id, user_id=user.id))
        video.like_count = (video.like_count or 0) + 1
        liked = True
    db.add(video)
    db.commit()
    db.refresh(video)
    return {"liked": liked, "like_count": video.like_count}


def toggle_favorite(db: Session, video_id: int, user: User) -> dict:
    video = video_service.get_video(db, video_id)
    if not video_service.can_view_detail(video, user):
        raise BizError("无权操作该视频", 403)
    row = (
        db.query(VideoFavorite)
        .filter(VideoFavorite.video_id == video_id, VideoFavorite.user_id == user.id)
        .first()
    )
    if row:
        db.delete(row)
        video.favorite_count = max((video.favorite_count or 0) - 1, 0)
        favorited = False
    else:
        db.add(VideoFavorite(video_id=video_id, user_id=user.id))
        video.favorite_count = (video.favorite_count or 0) + 1
        favorited = True
    db.add(video)
    db.commit()
    db.refresh(video)
    return {"favorited": favorited, "favorite_count": video.favorite_count}
