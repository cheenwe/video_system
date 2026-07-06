"""系统概览统计"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.sys_config import SysConfig
from src.models.sys_log import SysLog
from src.models.user import User
from src.models.video import (
    Video,
    VideoAlbum,
    VideoAlbumItem,
    VideoCategory,
    VideoComment,
    VideoFavorite,
    VideoLike,
    VideoUploadSession,
)


def _count(q) -> int:
    return int(q.scalar() or 0)


def get_dashboard_stats(db: Session) -> dict:
    users_total = _count(db.query(func.count(User.id)))
    users_active = _count(db.query(func.count(User.id)).filter(User.disabled == 0))
    users_disabled = _count(db.query(func.count(User.id)).filter(User.disabled != 0))
    users_admin = _count(db.query(func.count(User.id)).filter(User.role == "admin"))

    logs_total = _count(db.query(func.count(SysLog.id)))
    logs_login = _count(db.query(func.count(SysLog.id)).filter(SysLog.tag == "login"))
    logs_operation = _count(db.query(func.count(SysLog.id)).filter(SysLog.tag == "operation"))
    logs_audit = _count(db.query(func.count(SysLog.id)).filter(SysLog.tag == "audit"))

    videos_total = _count(db.query(func.count(Video.id)))
    videos_public = _count(db.query(func.count(Video.id)).filter(Video.visibility == "public"))
    videos_private = _count(db.query(func.count(Video.id)).filter(Video.visibility == "private"))
    videos_ready = _count(db.query(func.count(Video.id)).filter(Video.status == "ready"))
    views_total = _count(db.query(func.coalesce(func.sum(Video.view_count), 0)))

    albums_total = _count(db.query(func.count(VideoAlbum.id)))
    albums_public = _count(db.query(func.count(VideoAlbum.id)).filter(VideoAlbum.visibility == "public"))
    albums_private = _count(db.query(func.count(VideoAlbum.id)).filter(VideoAlbum.visibility == "private"))

    upload_total = _count(db.query(func.count(VideoUploadSession.id)))
    upload_uploading = _count(
        db.query(func.count(VideoUploadSession.id)).filter(VideoUploadSession.status == "uploading")
    )
    upload_completed = _count(
        db.query(func.count(VideoUploadSession.id)).filter(VideoUploadSession.status == "completed")
    )

    return {
        "system": {
            "users": {
                "total": users_total,
                "active": users_active,
                "disabled": users_disabled,
                "admins": users_admin,
            },
            "sys_configs": _count(db.query(func.count(SysConfig.id))),
            "sys_logs": {
                "total": logs_total,
                "login": logs_login,
                "operation": logs_operation,
                "audit": logs_audit,
            },
        },
        "video": {
            "videos": {
                "total": videos_total,
                "public": videos_public,
                "private": videos_private,
                "ready": videos_ready,
            },
            "categories": _count(db.query(func.count(VideoCategory.id))),
            "albums": {
                "total": albums_total,
                "public": albums_public,
                "private": albums_private,
            },
            "album_items": _count(db.query(func.count(VideoAlbumItem.id))),
            "comments": _count(db.query(func.count(VideoComment.id))),
            "likes": _count(db.query(func.count(VideoLike.id))),
            "favorites": _count(db.query(func.count(VideoFavorite.id))),
            "views_total": views_total,
            "upload_sessions": {
                "total": upload_total,
                "uploading": upload_uploading,
                "completed": upload_completed,
            },
        },
    }
