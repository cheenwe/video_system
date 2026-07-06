"""视频评论 API"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import get_client_ip, get_current_user, get_optional_user
from src.core.exceptions import ok
from src.models.user import User
from src.schemas.video_comment import VideoCommentCreateBody
from src.services import video_comment_service
from src.services.log_service import log_action

router = APIRouter(tags=["视频评论"])


@router.get("/api/videos/{video_id}/comments")
def api_list_comments(
    video_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    return ok(video_comment_service.list_comments(db, video_id, me, page=page, page_size=page_size))


@router.post("/api/videos/{video_id}/comments")
def api_create_comment(
    video_id: int,
    body: VideoCommentCreateBody,
    request: Request,
    db: Session = Depends(get_db),
    me: Optional[User] = Depends(get_optional_user),
):
    comment = video_comment_service.create_comment(
        db,
        video_id,
        content=body.content,
        anonymous=body.anonymous,
        display_name=body.display_name,
        user=me,
    )
    log_action(
        db,
        tag="operation",
        action="video_comment.create",
        user_id=me.id if me else None,
        username=me.username if me else comment.display_name,
        ip=get_client_ip(request),
        remark=f"video={video_id}",
    )
    out = {
        "id": comment.id,
        "display_name": comment.display_name,
        "content": comment.content,
        "is_anonymous": bool(comment.is_anonymous),
        "created_at": comment.created_at.isoformat(sep=" ", timespec="seconds") if comment.created_at else None,
    }
    return ok(out, msg="评论已发布")


@router.delete("/api/videos/{video_id}/comments/{comment_id}")
def api_delete_comment(
    video_id: int,
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    video_comment_service.delete_comment(db, video_id, comment_id, me)
    log_action(
        db,
        tag="operation",
        action="video_comment.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        remark=f"video={video_id} comment={comment_id}",
    )
    return ok(None, msg="已删除")
