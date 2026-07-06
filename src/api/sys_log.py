"""系统日志接口（只读，管理员）"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import require_admin
from src.core.exceptions import ok
from src.core.input_security import like_contains_pattern
from src.models.user import User
from src.models.sys_log import SysLog
from src.schemas.sys_log import SysLogOut

from src.services import sys_log_service

router = APIRouter(prefix="/api/sys-logs", tags=["系统日志"])


@router.get("/csv/export")
def api_export_sys_logs_csv(
    keyword: str | None = Query(default=None, max_length=100),
    user_id: int | None = None,
    tag: str | None = None,
    result: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    csv_text = sys_log_service.export_sys_logs_csv(
        db, keyword=keyword, user_id=user_id, tag=tag, result=result
    )
    body = "\ufeff" + csv_text
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sys_logs_export.csv"'},
    )


@router.get("")
def api_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    keyword: str | None = Query(default=None, max_length=100),
    user_id: int | None = None,
    tag: str | None = None,
    result: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(SysLog)
    like_info = like_contains_pattern(keyword)
    if like_info:
        like, esc = like_info
        q = q.filter(
            or_(
                SysLog.action.ilike(like, escape=esc),
                SysLog.username.ilike(like, escape=esc),
                SysLog.remark.ilike(like, escape=esc),
            )
        )
    if user_id:
        q = q.filter(SysLog.user_id == user_id)
    if tag:
        q = q.filter(SysLog.tag == tag)
    if result:
        q = q.filter(SysLog.result == result)
    total = q.count()
    items = q.order_by(SysLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok({"items": [SysLogOut.model_validate(x).model_dump() for x in items], "total": total, "page": page, "page_size": page_size})
