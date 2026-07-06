"""视频分类与专辑 API"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import get_client_ip, get_current_user, get_optional_user, require_admin
from src.core.exceptions import ok
from src.models.user import User
from src.models.video import Video
from src.schemas.video_taxonomy import (
    VideoAlbumEnsureBody,
    VideoAlbumBody,
    VideoAlbumItemBody,
    VideoAlbumUpdateBody,
    VideoCategoryBody,
    VideoCategoryEnsureBody,
    VideoCategoryUpdateBody,
)
from src.services import video_taxonomy_service
from src.services.log_service import log_action

router = APIRouter(tags=["视频分类与专辑"])


@router.get("/api/video-categories")
def api_list_categories(db: Session = Depends(get_db)):
    return ok(video_taxonomy_service.list_categories(db))


@router.post("/api/video-categories/ensure")
def api_ensure_category(
    body: VideoCategoryEnsureBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    existing = video_taxonomy_service.find_category_by_name(db, body.name)
    created = existing is None
    c = video_taxonomy_service.find_or_create_category(db, body.name, me)
    if created:
        log_action(
            db,
            tag="operation",
            action="video_category.ensure_create",
            user_id=me.id,
            username=me.username,
            ip=get_client_ip(request),
            remark=c.name,
        )
    return ok({"id": c.id, "name": c.name, "created": created})


@router.post("/api/video-categories")
def api_create_category(
    body: VideoCategoryBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    c = video_taxonomy_service.create_category(db, body.model_dump())
    log_action(
        db,
        tag="operation",
        action="video_category.create",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=c.name,
    )
    return ok({"id": c.id, "name": c.name})


@router.put("/api/video-categories/{category_id}")
def api_update_category(
    category_id: int,
    body: VideoCategoryUpdateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    c = video_taxonomy_service.update_category(db, category_id, body.model_dump(exclude_unset=True))
    log_action(
        db,
        tag="operation",
        action="video_category.update",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=c.name,
    )
    cnt = db.query(Video).filter(Video.category_id == c.id).count()
    return ok(video_taxonomy_service._serialize_category(c, video_count=cnt))  # noqa: SLF001


@router.delete("/api/video-categories/{category_id}")
def api_delete_category(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    video_taxonomy_service.delete_category(db, category_id)
    log_action(
        db,
        tag="audit",
        action="video_category.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"ID {category_id}",
    )
    return ok(None, msg="已删除")


@router.get("/api/video-albums")
def api_list_albums(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=100),
    visibility: str | None = Query("public", description="public | private | mine | all"),
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    items, total = video_taxonomy_service.list_albums(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        visibility=visibility,
        user=me,
    )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.post("/api/video-albums/ensure")
def api_ensure_album(
    body: VideoAlbumEnsureBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    existing = video_taxonomy_service.find_album_by_title(db, body.title, me)
    created = existing is None
    album = video_taxonomy_service.find_or_create_album(
        db, body.title, me, visibility=body.visibility
    )
    if created:
        log_action(
            db,
            tag="operation",
            action="video_album.ensure_create",
            user_id=me.id,
            username=me.username,
            ip=get_client_ip(request),
            remark=album.title,
        )
    return ok({"id": album.id, "title": album.title, "created": created})


@router.get("/api/video-albums/{album_id}")
def api_album_detail(
    album_id: int,
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    return ok(video_taxonomy_service.album_detail(db, album_id, me))


@router.post("/api/video-albums")
def api_create_album(
    body: VideoAlbumBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    album = video_taxonomy_service.create_album(db, body.model_dump(), me)
    log_action(
        db,
        tag="operation",
        action="video_album.create",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=album.title,
    )
    return ok(video_taxonomy_service._serialize_album(db, album, me))  # noqa: SLF001


@router.put("/api/video-albums/{album_id}")
def api_update_album(
    album_id: int,
    body: VideoAlbumUpdateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    album = video_taxonomy_service.update_album(db, album_id, body.model_dump(exclude_unset=True), me)
    log_action(
        db,
        tag="operation",
        action="video_album.update",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=album.title,
    )
    return ok(video_taxonomy_service._serialize_album(db, album, me))  # noqa: SLF001


@router.delete("/api/video-albums/{album_id}")
def api_delete_album(
    album_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    video_taxonomy_service.delete_album(db, album_id, me)
    log_action(
        db,
        tag="audit",
        action="video_album.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"ID {album_id}",
    )
    return ok(None, msg="已删除")


@router.post("/api/video-albums/{album_id}/videos")
def api_album_add_video(
    album_id: int,
    body: VideoAlbumItemBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    video_taxonomy_service.add_video_to_album(db, album_id, body.video_id, body.sort_order, me)
    log_action(
        db,
        tag="operation",
        action="video_album.add_video",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"album={album_id} video={body.video_id}",
    )
    return ok(None, msg="已加入专辑")


@router.delete("/api/video-albums/{album_id}/videos/{video_id}")
def api_album_remove_video(
    album_id: int,
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    video_taxonomy_service.remove_video_from_album(db, album_id, video_id, me)
    log_action(
        db,
        tag="operation",
        action="video_album.remove_video",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"album={album_id} video={video_id}",
    )
    return ok(None, msg="已移出专辑")
