"""系统日志导出"""
from __future__ import annotations

import csv
from io import StringIO
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.core.input_security import like_contains_pattern
from src.models.sys_log import SysLog


def export_sys_logs_csv(
    db: Session,
    *,
    keyword: Optional[str] = None,
    user_id: Optional[int] = None,
    tag: Optional[str] = None,
    result: Optional[str] = None,
    max_rows: int = 100000,
) -> str:
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
    items = q.order_by(SysLog.id.desc()).limit(max_rows).all()
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "created_at", "ip", "user_id", "username", "tag", "result", "action", "request_id", "remark"])
    for x in items:
        ca = x.created_at.isoformat() if x.created_at else ""
        w.writerow(
            [
                x.id,
                ca,
                x.ip or "",
                x.user_id or "",
                x.username or "",
                x.tag,
                x.result,
                x.action,
                x.request_id or "",
                (x.remark or "").replace("\r\n", " ").replace("\n", " "),
            ]
        )
    return buf.getvalue()
