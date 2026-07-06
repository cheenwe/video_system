"""用户管理接口（管理员）"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import get_client_ip, get_current_user, get_request_id, require_admin
from src.core.exceptions import BizError, ok
from src.models.user import User
from src.schemas.password import ResetPasswordRequest
from src.schemas.user import UserCreate, UserOut, UserUpdate
from src.services import user_service
from src.services.log_service import log_action

router = APIRouter(prefix="/api/users", tags=["用户"])


@router.get("/csv/export")
def api_export_users_csv(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    csv_text = user_service.export_users_csv(db)
    body = "\ufeff" + csv_text
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="users_export.csv"'},
    )


@router.post("/csv/import")
async def api_import_users_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise BizError("文件须为 UTF-8 编码的 CSV") from e
    data = user_service.import_users_from_csv(db, text)
    log_action(
        db,
        tag="audit",
        action="user.import_csv",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
        remark=f"+{data['created']} ~{data['updated']}",
    )
    return ok(data, msg="导入完成")


@router.get("")
def api_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    items, total = user_service.list_users(db, page, page_size, keyword)
    return ok({"items": [UserOut.model_validate(u).model_dump() for u in items], "total": total, "page": page, "page_size": page_size})


@router.post("")
def api_create(
    data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    u = user_service.create_user(db, data)
    log_action(db, tag="operation", action="user.create", user_id=me.id, username=me.username, ip=get_client_ip(request), remark=f"创建用户 {u.username}")
    return ok(UserOut.model_validate(u).model_dump(), msg="创建成功")


@router.put("/{uid}")
def api_update(
    uid: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    u = user_service.update_user(db, uid, data)
    log_action(db, tag="operation", action="user.update", user_id=me.id, username=me.username, ip=get_client_ip(request), remark=f"更新用户 {u.username}")
    return ok(UserOut.model_validate(u).model_dump(), msg="保存成功")


@router.post("/{uid}/disabled")
def api_disabled(
    uid: int,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    disabled = bool(body.get("disabled", False))
    u = user_service.set_disabled(db, uid, disabled)
    log_action(db, tag="audit", action="user.disabled", user_id=me.id, username=me.username, ip=get_client_ip(request), remark=f"{'禁用' if disabled else '启用'} {u.username}")
    return ok(UserOut.model_validate(u).model_dump(), msg="已禁用" if disabled else "已启用")


@router.delete("/{uid}")
def api_delete(
    uid: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    user_service.delete_user(db, uid, me.id)
    log_action(
        db,
        tag="audit",
        action="user.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
        remark=f"删除用户ID {uid}",
    )
    return ok(msg="已删除")


@router.post("/{uid}/reset-password")
def api_reset_password(
    uid: int,
    data: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    u = user_service.reset_password(db, uid, data.new_password)
    log_action(db, tag="audit", action="user.reset_password", user_id=me.id, username=me.username, ip=get_client_ip(request), remark=f"重置用户 {u.username} 密码")
    return ok(msg="密码已重置")
