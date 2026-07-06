"""视频查询、权限与播放"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional, Tuple

from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.deps import is_admin
from src.core.exceptions import BizError
from src.core.input_security import like_contains_pattern
from src.models.user import User
from src.models.video import Video, VideoCategory
from src.services import video_taxonomy_service
from src.services.video_ref_service import VideoAccessContext, encode_video_ref


def hub_config() -> dict:
    from src.services import video_cover_service

    return {
        "allow_anonymous_play": settings.VIDEO_ALLOW_ANONYMOUS_PLAY,
        "max_upload_mb": settings.VIDEO_MAX_UPLOAD_MB,
        "chunk_size_mb": settings.VIDEO_CHUNK_SIZE_MB,
        "cover_width": video_cover_service.COVER_WIDTH,
        "cover_height": video_cover_service.COVER_HEIGHT,
    }


def video_abs_path(video: Video) -> Path:
    return settings.resolve_upload_file(video.file_path)


def can_play_video(video: Video, user: Optional[User], access: VideoAccessContext | None = None) -> bool:
    if access and access.grants_public_play() and access.video_id == video.id:
        return video.status == "ready"
    if video.visibility == "private":
        return user is not None
    if settings.VIDEO_ALLOW_ANONYMOUS_PLAY:
        return True
    return user is not None


def can_view_detail(video: Video, user: Optional[User], access: VideoAccessContext | None = None) -> bool:
    if access and access.grants_public_play() and access.video_id == video.id:
        return True
    if video.visibility == "private":
        return user is not None
    return True


def assert_can_play(video: Video, user: Optional[User], access: VideoAccessContext | None = None) -> None:
    if access and access.grants_public_play() and access.video_id == video.id:
        if video.status != "ready":
            raise BizError("视频尚未就绪", 404)
        return
    if video.status != "ready":
        raise BizError("视频尚未就绪", 404)
    if video.visibility == "private" and user is None:
        raise BizError("该视频为隐私内容，请登录后观看", 401)
    if video.visibility == "public" and not settings.VIDEO_ALLOW_ANONYMOUS_PLAY and user is None:
        raise BizError("站点已关闭游客播放，请登录后观看", 401)
    if not can_play_video(video, user):
        raise BizError("无权播放该视频", 403)


def get_video(db: Session, video_id: int) -> Video:
    v = db.get(Video, video_id)
    if not v:
        raise BizError("视频不存在", 404)
    return v


def can_manage_video(video: Video, user: User) -> bool:
    """管理员可管理全部视频；普通用户仅可管理自己上传的视频。"""
    if is_admin(user):
        return True
    if video.uploader_id is None:
        return False
    return int(video.uploader_id) == int(user.id)


def assert_can_manage_video(video: Video, user: User) -> None:
    if not can_manage_video(video, user):
        raise BizError("无权管理该视频", 403)


def list_videos(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    visibility: str | None,
    user: Optional[User],
    exclude_id: int | None = None,
    category_id: int | None = None,
    album_id: int | None = None,
) -> Tuple[list[dict], int]:
    q = db.query(Video).filter(Video.status == "ready")

    vis = (visibility or "public").strip().lower()
    if vis not in {"public", "private", "all", "mine"}:
        vis = "public"

    if vis == "public":
        q = q.filter(Video.visibility == "public")
    elif vis == "private":
        if user is None:
            raise BizError("查看隐私视频请先登录", 401)
        q = q.filter(Video.visibility == "private")
    elif vis == "mine":
        if user is None:
            raise BizError("请先登录", 401)
        q = q.filter(Video.uploader_id == user.id)
    elif vis == "all":
        if user is None:
            raise BizError("请先登录", 401)
        if not is_admin(user):
            raise BizError("无权查看全部视频", 403)

    if exclude_id:
        q = q.filter(Video.id != exclude_id)

    if category_id:
        q = q.filter(Video.category_id == category_id)

    if album_id:
        from src.models.video import VideoAlbumItem

        q = q.join(VideoAlbumItem, VideoAlbumItem.video_id == Video.id).filter(
            VideoAlbumItem.album_id == album_id
        )

    like_info = like_contains_pattern(keyword)
    if like_info:
        like, esc = like_info
        q = q.filter(
            or_(Video.title.like(like, escape=esc), Video.description.like(like, escape=esc))
        )

    total = q.count()
    items = (
        q.order_by(Video.view_count.desc(), Video.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_serialize_video(db, v, user) for v in items], total


def _serialize_video(
    db: Session,
    video: Video,
    user: Optional[User],
    access: VideoAccessContext | None = None,
) -> dict:
    can_play = can_play_video(video, user, access)
    created = video.created_at.isoformat(sep=" ", timespec="seconds") if video.created_at else None
    uploader_name = None
    if video.uploader_id:
        u = db.get(User, video.uploader_id)
        uploader_name = (u.real_name or u.username) if u else None
    category_name = None
    if video.category_id:
        cat = db.get(VideoCategory, video.category_id)
        category_name = cat.name if cat else None
    albums = video_taxonomy_service.albums_for_video(db, video.id, user)
    from src.services import video_interaction_service

    flags = video_interaction_service.user_flags(db, video.id, user.id if user else None)
    return {
        "id": video.id,
        "ref": encode_video_ref(video.id),
        "title": video.title,
        "description": video.description,
        "visibility": video.visibility,
        "status": video.status,
        "mime_type": video.mime_type,
        "file_size": video.file_size,
        "duration_sec": video.duration_sec,
        "view_count": video.view_count,
        "like_count": video.like_count or 0,
        "favorite_count": video.favorite_count or 0,
        "liked": flags["liked"],
        "favorited": flags["favorited"],
        "category_id": video.category_id,
        "category_name": category_name,
        "albums": albums,
        "uploader_id": video.uploader_id,
        "uploader_name": uploader_name,
        "original_filename": video.original_filename,
        "created_at": created,
        "can_play": can_play,
        "play_url": f"/api/videos/{video.id}/stream" if can_play else None,
        "cover_url": _cover_url(video),
        "require_login": not can_play and video.visibility == "private",
        "can_manage": can_manage_video(video, user) if user else False,
    }


def _cover_url(video: Video) -> str | None:
    from src.services import video_cover_service

    return video_cover_service.cover_url(video)


def video_detail(
    db: Session,
    video_id: int,
    user: Optional[User],
    access: VideoAccessContext | None = None,
) -> dict:
    v = get_video(db, video_id)
    if not can_view_detail(v, user, access):
        raise BizError("该视频为隐私内容，请登录后查看", 401)
    out = _serialize_video(db, v, user, access)
    if not out["can_play"]:
        if v.visibility == "private":
            out["play_block_reason"] = "login_required_private"
        elif not settings.VIDEO_ALLOW_ANONYMOUS_PLAY:
            out["play_block_reason"] = "login_required_site_policy"
        else:
            out["play_block_reason"] = "forbidden"
    return out


def increment_view(db: Session, video: Video) -> int:
    video.view_count = (video.view_count or 0) + 1
    db.add(video)
    db.commit()
    db.refresh(video)
    return video.view_count


def update_video(db: Session, video_id: int, data: dict, user: User) -> Video:
    v = get_video(db, video_id)
    assert_can_manage_video(v, user)
    if data.get("title") is not None:
        v.title = str(data["title"]).strip()
    if data.get("description") is not None:
        v.description = str(data["description"] or "").strip()
    if data.get("visibility") is not None:
        vis = str(data["visibility"])
        if vis in {"public", "private"}:
            v.visibility = vis
    if "category_id" in data:
        cid = data.get("category_id")
        if cid is None:
            v.category_id = None
        else:
            video_taxonomy_service.validate_category_id(db, int(cid))
            v.category_id = int(cid)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def delete_video(db: Session, video_id: int, user: User) -> None:
    v = get_video(db, video_id)
    assert_can_manage_video(v, user)
    from src.services import video_cover_service

    video_cover_service.delete_cover_file(v)
    path = video_abs_path(v)
    db.delete(v)
    db.commit()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def stream_media_type(video: Video) -> str:
    if video.mime_type:
        mt = video.mime_type.lower()
        if mt == "video/quicktime" or video.file_path.lower().endswith(".mp4"):
            return "video/mp4"
        return video.mime_type
    guessed, _ = mimetypes.guess_type(video.original_filename or video.file_path)
    return guessed or "video/mp4"


def build_stream_response(video: Video, path: Path, request: Request) -> Response:
    """Range 分块流式输出，支持弱网边下边播。"""
    from src.core.video_streaming import build_video_stream_response

    return build_video_stream_response(request, path, stream_media_type(video))
