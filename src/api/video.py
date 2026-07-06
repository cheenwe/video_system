"""视频与断点续传上传 API"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import get_client_ip, get_current_user, get_optional_user, get_request_id
from src.core.exceptions import BizError, ok
from src.models.user import User
from src.schemas.video import VideoCreateBody, VideoReplaceBody, VideoShareCreateBody, VideoUpdateBody, VideoUploadInitBody
from src.services import video_interaction_service, video_cover_service, video_service, video_taxonomy_service, video_upload_service
from src.services.video_ref_service import (
    create_public_share_link,
    encode_video_ref,
    resolve_access_token,
    serialize_share_link,
    try_resolve_access_token,
)
from src.services.log_service import log_action

router = APIRouter(tags=["视频"])


@router.get("/api/videos/config")
def api_video_config():
    return ok(video_service.hub_config())


@router.post("/api/videos/uploads/init")
def api_upload_init(
    body: VideoUploadInitBody,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    session = video_upload_service.init_upload(
        db,
        filename=body.filename,
        file_size=body.file_size,
        mime_type=body.mime_type,
        chunk_size=body.chunk_size,
        user_id=me.id,
    )
    received = video_upload_service.received_chunk_indices(session)
    return ok(
        {
            "upload_id": session.upload_id,
            "chunk_size": session.chunk_size,
            "total_chunks": session.total_chunks,
            "received_chunks": sorted(received),
        }
    )


@router.get("/api/videos/uploads/{upload_id}")
def api_upload_status(
    upload_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    session = video_upload_service.get_upload_session(db, upload_id)
    if session.user_id and session.user_id != me.id and (me.role or "").lower() != "admin":
        raise BizError("无权查看该上传任务", 403)
    received = video_upload_service.received_chunk_indices(session)
    return ok(
        {
            "upload_id": session.upload_id,
            "filename": session.filename,
            "file_size": session.file_size,
            "chunk_size": session.chunk_size,
            "total_chunks": session.total_chunks,
            "received_chunks": sorted(received),
            "status": session.status,
        }
    )


@router.put("/api/videos/uploads/{upload_id}/chunks/{chunk_index}")
async def api_upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    data = await request.body()
    received = video_upload_service.save_chunk(db, upload_id, chunk_index, data, me.id)
    return ok({"received_chunks": sorted(received), "chunk_index": chunk_index})


@router.put("/api/videos/uploads/{upload_id}/cover")
async def api_upload_pending_cover(
    upload_id: str,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    session = video_upload_service.get_upload_session(db, upload_id)
    if session.user_id and session.user_id != me.id and (me.role or "").lower() != "admin":
        raise BizError("无权上传该封面", 403)
    data = await request.body()
    video_cover_service.save_pending_cover(upload_id, data)
    return ok({"upload_id": upload_id}, msg="封面上传成功")


@router.delete("/api/videos/uploads/{upload_id}/cover")
def api_delete_pending_cover(
    upload_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    session = video_upload_service.get_upload_session(db, upload_id)
    if session.user_id and session.user_id != me.id and (me.role or "").lower() != "admin":
        raise BizError("无权删除该封面", 403)
    video_cover_service.remove_pending_cover(upload_id)
    return ok(None, msg="已移除封面")


@router.post("/api/videos")
def api_create_video(
    body: VideoCreateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    category_id = video_taxonomy_service.resolve_category_for_upload(
        db,
        me,
        category_id=body.category_id,
        category_name=body.category_name,
    )
    album_id = video_taxonomy_service.resolve_album_for_upload(
        db,
        me,
        album_id=body.album_id,
        album_title=body.album_title,
        visibility=body.visibility,
    )
    video = video_upload_service.complete_video_record(
        db,
        upload_id=body.upload_id,
        title=body.title,
        description=body.description,
        visibility=body.visibility,
        user_id=me.id,
        category_id=category_id,
        album_id=album_id,
    )
    log_action(
        db,
        tag="operation",
        action="video.create",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=video.title,
    )
    return ok(video_service._serialize_video(db, video, me))  # noqa: SLF001


@router.get("/api/videos")
def api_list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=100),
    visibility: str | None = Query("public", description="public | private | all | mine"),
    exclude_id: int | None = None,
    category_id: int | None = None,
    album_id: int | None = None,
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    items, total = video_service.list_videos(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        visibility=visibility,
        user=me,
        exclude_id=exclude_id,
        category_id=category_id,
        album_id=album_id,
    )
    data = video_service.hub_config()
    data.update({"items": items, "total": total, "page": page, "page_size": page_size})
    return ok(data)


@router.get("/api/videos/access")
def api_video_access(
    v: str = Query(..., min_length=8, max_length=512),
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    ctx = resolve_access_token(db, v)
    out = video_service.video_detail(db, ctx.video_id, me, ctx)
    out["access_v"] = v
    if ctx.share_link and ctx.share_link.public_access:
        out["share_public"] = True
        if ctx.share_link.expires_at:
            out["share_expires_at"] = ctx.share_link.expires_at.isoformat(sep=" ", timespec="seconds")
    return ok(out)


@router.get("/api/videos/{video_id}")
def api_video_detail(
    video_id: int,
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    return ok(video_service.video_detail(db, video_id, me))


@router.post("/api/videos/{video_id}/view")
def api_record_video_view(
    video_id: int,
    v: str | None = Query(None, max_length=512),
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    access = resolve_access_token(db, v) if v else None
    if access and access.video_id != video_id:
        raise BizError("访问令牌与视频不匹配", 403)
    video = video_service.get_video(db, video_id)
    video_service.assert_can_play(video, me, access)
    view_count = video_service.increment_view(db, video)
    return ok({"view_count": view_count})


@router.post("/api/videos/{video_id}/like")
def api_toggle_video_like(
    video_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    return ok(video_interaction_service.toggle_like(db, video_id, me))


@router.post("/api/videos/{video_id}/favorite")
def api_toggle_video_favorite(
    video_id: int,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    return ok(video_interaction_service.toggle_favorite(db, video_id, me))


@router.get("/api/videos/{video_id}/cover")
def api_video_cover(
    video_id: int,
    v: str | None = Query(None, max_length=512),
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    access = try_resolve_access_token(db, v)
    if access and access.video_id != video_id:
        raise BizError("访问令牌与视频不匹配", 403)
    video = video_service.get_video(db, video_id)
    if not video_service.can_view_detail(video, me, access):
        raise BizError("无权查看该视频封面", 403)
    path = video_cover_service.cover_abs_path(video)
    if not path:
        raise BizError("封面不存在", 404)
    return FileResponse(
        str(path),
        media_type="image/jpeg",
        filename=f"cover_{video_id}.jpg",
        stat_result=path.stat(),
    )


@router.get("/api/videos/{video_id}/stream")
def api_video_stream(
    video_id: int,
    v: str | None = Query(None, max_length=512),
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    access = resolve_access_token(db, v) if v else None
    if access and access.video_id != video_id:
        raise BizError("访问令牌与视频不匹配", 403)
    video = video_service.get_video(db, video_id)
    video_service.assert_can_play(video, me, access)
    path = video_service.video_abs_path(video)
    if not path.is_file():
        raise BizError("视频文件不存在", 404)
    return video_service.build_stream_response(video, path)


@router.put("/api/videos/{video_id}")
def api_update_video(
    video_id: int,
    body: VideoUpdateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    v = video_service.update_video(db, video_id, body.model_dump(exclude_unset=True), me)
    log_action(
        db,
        tag="operation",
        action="video.update",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=v.title,
    )
    return ok(video_service._serialize_video(db, v, me))  # noqa: SLF001


@router.post("/api/videos/{video_id}/share")
def api_create_video_share(
    video_id: int,
    body: VideoShareCreateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    video = video_service.get_video(db, video_id)
    if not video_service.can_view_detail(video, me):
        raise BizError("无权分享该视频", 403)
    if body.public_access:
        if not body.expires_hours:
            raise BizError("公开分享须设置有效期", 400)
        if not video_service.can_manage_video(video, me):
            raise BizError("仅视频上传者或管理员可创建公开分享链接", 403)
        link = create_public_share_link(
            db,
            video_id=video_id,
            user=me,
            expires_hours=int(body.expires_hours),
        )
        data = serialize_share_link(link)
        data["v"] = link.token
        data["path"] = "/video?v=" + link.token
    else:
        ref = encode_video_ref(video_id)
        data = {
            "v": ref,
            "public_access": False,
            "expires_at": None,
            "path": "/video?v=" + ref,
        }
    log_action(
        db,
        tag="operation",
        action="video.share",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"{video.title} public={int(body.public_access)}",
    )
    return ok(data)


@router.put("/api/videos/{video_id}/cover")
async def api_update_video_cover(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    v = video_service.get_video(db, video_id)
    video_service.assert_can_manage_video(v, me)
    data = await request.body()
    video_cover_service.save_video_cover(v, data)
    db.add(v)
    db.commit()
    db.refresh(v)
    log_action(
        db,
        tag="operation",
        action="video.cover.update",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=v.title,
    )
    return ok(video_service._serialize_video(db, v, me))  # noqa: SLF001


@router.delete("/api/videos/{video_id}/cover")
def api_delete_video_cover(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    v = video_service.get_video(db, video_id)
    video_service.assert_can_manage_video(v, me)
    video_cover_service.delete_cover_file(v)
    db.add(v)
    db.commit()
    log_action(
        db,
        tag="operation",
        action="video.cover.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=v.title,
    )
    return ok(None, msg="已移除封面")


@router.post("/api/videos/{video_id}/replace")
def api_replace_video_file(
    video_id: int,
    body: VideoReplaceBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    v = video_service.get_video(db, video_id)
    video_service.assert_can_manage_video(v, me)
    v = video_upload_service.replace_video_file(
        db,
        video_id=video_id,
        upload_id=body.upload_id,
        user=me,
    )
    log_action(
        db,
        tag="operation",
        action="video.replace",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=v.title,
    )
    return ok(video_service._serialize_video(db, v, me))  # noqa: SLF001


@router.delete("/api/videos/{video_id}")
def api_delete_video(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    video_service.delete_video(db, video_id, me)
    log_action(
        db,
        tag="audit",
        action="video.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"ID {video_id}",
    )
    return ok(None, msg="已删除")
