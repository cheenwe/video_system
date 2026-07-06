"""视频分片上传（断点续传）"""
from __future__ import annotations

import math
import os
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BizError
from src.core.input_security import like_contains_pattern, sanitize_filename, validate_upload_id
from src.models.user import User
from src.models.video import Video, VideoUploadSession


def _chunks_dir(upload_id: str) -> Path:
    p = settings.video_chunks_root_path / upload_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _videos_dir() -> Path:
    p = settings.video_files_root_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_received(raw: str) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _serialize_received(chunks: set[int]) -> str:
    if not chunks:
        return ""
    return ",".join(str(x) for x in sorted(chunks))


def _guess_mime(filename: str, fallback: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".m4v": "video/mp4",
    }
    return mapping.get(ext, fallback or "application/octet-stream")


def init_upload(
    db: Session,
    *,
    filename: str,
    file_size: int,
    mime_type: str,
    chunk_size: int | None,
    user_id: int | None,
) -> VideoUploadSession:
    max_bytes = settings.VIDEO_MAX_UPLOAD_BYTES
    if file_size > max_bytes:
        raise BizError(f"文件过大，最大允许 {settings.VIDEO_MAX_UPLOAD_MB}MB")

    name = sanitize_filename(filename or "")

    cs = chunk_size or settings.VIDEO_CHUNK_SIZE_BYTES
    cs = max(256 * 1024, min(cs, 20 * 1024 * 1024))
    total = max(1, math.ceil(file_size / cs))

    upload_id = uuid4().hex
    session = VideoUploadSession(
        upload_id=upload_id,
        filename=name,
        mime_type=_guess_mime(name, mime_type),
        file_size=file_size,
        chunk_size=cs,
        total_chunks=total,
        received_chunks="",
        user_id=user_id,
        status="uploading",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    _chunks_dir(upload_id)
    return session


def get_upload_session(db: Session, upload_id: str) -> VideoUploadSession:
    upload_id = validate_upload_id(upload_id)
    s = db.query(VideoUploadSession).filter(VideoUploadSession.upload_id == upload_id).first()
    if not s:
        raise BizError("上传任务不存在或已过期", 404)
    return s


def save_chunk(db: Session, upload_id: str, chunk_index: int, data: bytes, user_id: int | None) -> set[int]:
    session = get_upload_session(db, upload_id)
    if session.status != "uploading":
        raise BizError("上传任务已结束，无法继续写入分片")
    if user_id is not None and session.user_id is not None and session.user_id != user_id:
        raise BizError("无权续传该上传任务", 403)
    if chunk_index < 0 or chunk_index >= session.total_chunks:
        raise BizError("分片序号无效")

    if not data:
        raise BizError("分片内容为空")

    chunk_path = _chunks_dir(upload_id) / f"{chunk_index:06d}.part"
    chunk_path.write_bytes(data)

    received = _parse_received(session.received_chunks)
    received.add(chunk_index)
    session.received_chunks = _serialize_received(received)
    db.add(session)
    db.commit()
    return received


def merge_upload(db: Session, upload_id: str, user_id: int | None) -> Path:
    session = get_upload_session(db, upload_id)
    if session.status != "uploading":
        raise BizError("上传任务已合并")
    if user_id is not None and session.user_id is not None and session.user_id != user_id:
        raise BizError("无权完成该上传任务", 403)

    received = _parse_received(session.received_chunks)
    if len(received) != session.total_chunks:
        missing = [i for i in range(session.total_chunks) if i not in received]
        preview = missing[:10]
        suffix = "..." if len(missing) > 10 else ""
        raise BizError(f"分片未传齐，缺少: {preview}{suffix}")

    ext = Path(session.filename).suffix or ".mp4"
    final_name = f"{upload_id}{ext}"
    final_path = _videos_dir() / final_name

    with final_path.open("wb") as out:
        for i in range(session.total_chunks):
            part = _chunks_dir(upload_id) / f"{i:06d}.part"
            if not part.is_file():
                raise BizError(f"分片文件缺失: {i}")
            with part.open("rb") as inp:
                shutil.copyfileobj(inp, out)

    actual_size = final_path.stat().st_size
    if actual_size != session.file_size:
        # 允许末分片不足 chunk_size 导致轻微差异时以实际为准；明显不一致则报错
        if abs(actual_size - session.file_size) > session.chunk_size:
            final_path.unlink(missing_ok=True)
            raise BizError(f"合并后大小不符，期望 {session.file_size} 实际 {actual_size}")

    session.status = "merged"
    db.add(session)
    db.commit()

    shutil.rmtree(_chunks_dir(upload_id), ignore_errors=True)
    return final_path


def complete_video_record(
    db: Session,
    *,
    upload_id: str,
    title: str,
    description: str,
    visibility: str,
    user_id: int | None,
    category_id: int | None = None,
    album_id: int | None = None,
) -> Video:
    session = get_upload_session(db, upload_id)
    if session.status == "uploading":
        merge_upload(db, upload_id, user_id)
        db.refresh(session)

    if session.status != "merged":
        raise BizError("上传任务状态异常")

    ext = Path(session.filename).suffix or ".mp4"
    final_name = f"{upload_id}{ext}"
    final_path = _videos_dir() / final_name
    if not final_path.is_file():
        raise BizError("视频文件不存在，请重新上传")

    from src.services import video_transcode_service

    prepared = video_transcode_service.prepare_for_web_playback(final_path, upload_id)
    rel_path = str(prepared.path.relative_to(settings.upload_root_path)).replace("\\", "/")
    vis = visibility if visibility in {"public", "private"} else "public"

    from src.services import video_taxonomy_service

    if category_id:
        video_taxonomy_service.validate_category_id(db, category_id)

    video = Video(
        title=title.strip(),
        description=(description or "").strip(),
        visibility=vis,
        status="ready",
        file_path=rel_path,
        original_filename=session.filename,
        mime_type=prepared.mime_type,
        file_size=prepared.file_size,
        duration_sec=prepared.duration_sec,
        uploader_id=user_id,
        category_id=category_id,
    )
    db.add(video)
    session.status = "completed"
    db.add(session)
    db.commit()
    db.refresh(video)
    if album_id and user_id:
        from src.models.user import User

        user = db.get(User, user_id)
        if user:
            video_taxonomy_service.attach_video_to_album_on_create(db, video, album_id, user)

    from src.services import video_cover_service

    video_cover_service.attach_pending_cover(upload_id, video)
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def replace_video_file(
    db: Session,
    *,
    video_id: int,
    upload_id: str,
    user: User,
) -> Video:
    from src.services.video_service import assert_can_manage_video, get_video, video_abs_path

    video = get_video(db, video_id)
    assert_can_manage_video(video, user)
    user_id = user.id
    session = get_upload_session(db, upload_id)
    if session.status == "uploading":
        merge_upload(db, upload_id, user_id)
        db.refresh(session)
    if session.status != "merged":
        raise BizError("上传任务状态异常，请完成文件上传后再替换")

    ext = Path(session.filename).suffix or ".mp4"
    new_path = _videos_dir() / f"{upload_id}{ext}"
    if not new_path.is_file():
        raise BizError("新视频文件不存在，请重新上传")

    from src.services import video_transcode_service

    prepared = video_transcode_service.prepare_for_web_playback(new_path, upload_id)
    old_path = video_abs_path(video)
    rel_path = str(prepared.path.relative_to(settings.upload_root_path)).replace("\\", "/")

    video.file_path = rel_path
    video.original_filename = session.filename
    video.mime_type = prepared.mime_type
    video.file_size = prepared.file_size
    video.duration_sec = prepared.duration_sec
    video.status = "ready"

    session.status = "completed"
    db.add(session)
    db.add(video)
    db.commit()
    db.refresh(video)

    if old_path.is_file() and old_path.resolve() != prepared.path.resolve():
        try:
            old_path.unlink()
        except OSError:
            pass
    return video


def received_chunk_indices(session: VideoUploadSession) -> list[int]:
    return sorted(_parse_received(session.received_chunks))


def cleanup_stale_chunks(max_age_hours: int = 48) -> None:
    """可选：清理长期未完成的分片目录（暂不挂定时任务）。"""
    root = settings.video_chunks_root_path
    if not root.is_dir():
        return
    import time

    cutoff = time.time() - max_age_hours * 3600
    for child in root.iterdir():
        if child.is_dir() and child.stat().st_mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)
