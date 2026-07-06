"""视频封面存储与关联"""
from __future__ import annotations

from pathlib import Path

from src.core.config import settings
from src.core.exceptions import BizError
from src.models.video import Video

COVER_WIDTH = 640
COVER_HEIGHT = 360
MAX_COVER_BYTES = 512 * 1024
JPEG_MAGIC = b"\xff\xd8\xff"


def _covers_dir() -> Path:
    p = settings.video_covers_root_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pending_dir() -> Path:
    p = _covers_dir() / "pending"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pending_cover_path(upload_id: str) -> Path:
    return _pending_dir() / f"{upload_id}.jpg"


def final_cover_path(video_id: int) -> Path:
    return _covers_dir() / f"{video_id}.jpg"


def cover_rel_path(video_id: int) -> str:
    rel = final_cover_path(video_id).relative_to(settings.upload_root_path)
    return str(rel).replace("\\", "/")


def cover_abs_path(video: Video) -> Path | None:
    if video.cover_path:
        p = settings.resolve_upload_file(video.cover_path)
        return p if p.is_file() else None
    legacy = final_cover_path(video.id)
    return legacy if legacy.is_file() else None


def cover_url(video: Video) -> str | None:
    path = cover_abs_path(video)
    if not path:
        return None
    return f"/api/videos/{video.id}/cover?t={path.stat().st_mtime_ns}"


def validate_cover_bytes(data: bytes) -> None:
    if not data:
        raise BizError("封面文件为空")
    if len(data) > MAX_COVER_BYTES:
        raise BizError("封面文件过大，最大 512KB")
    if not data.startswith(JPEG_MAGIC):
        raise BizError("封面须为 JPEG 格式（640×360）")


def save_pending_cover(upload_id: str, data: bytes) -> None:
    validate_cover_bytes(data)
    pending_cover_path(upload_id).write_bytes(data)


def attach_pending_cover(upload_id: str, video: Video) -> None:
    pending = pending_cover_path(upload_id)
    if not pending.is_file():
        return
    dest = final_cover_path(video.id)
    dest.write_bytes(pending.read_bytes())
    pending.unlink(missing_ok=True)
    video.cover_path = cover_rel_path(video.id)


def delete_cover_file(video: Video) -> None:
    path = cover_abs_path(video)
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    video.cover_path = None


def remove_pending_cover(upload_id: str) -> None:
    pending_cover_path(upload_id).unlink(missing_ok=True)


def save_video_cover(video: Video, data: bytes) -> None:
    validate_cover_bytes(data)
    dest = final_cover_path(video.id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    video.cover_path = cover_rel_path(video.id)
