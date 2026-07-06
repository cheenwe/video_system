"""系统配置接口"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.deps import get_client_ip, get_current_user, get_request_id, require_admin
from src.core.exceptions import BizError, ok
from src.models.user import User
from src.schemas.sys_config import SysConfigCreate, SysConfigOut, SysConfigUpdate
from src.services import sys_config_service
from src.services.log_service import log_action

router = APIRouter(prefix="/api/sys-configs", tags=["系统配置"])


@router.get("/value")
def api_get_config_value(
    category: str = Query(..., min_length=1),
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """白名单键：供前端动态加载系统配置。"""
    data = sys_config_service.get_public_config_payload(db, category, code)
    return ok(data)


@router.get("/csv/export")
def api_export_sys_configs_csv(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    csv_text = sys_config_service.export_sys_configs_csv(db)
    body = "\ufeff" + csv_text
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sys_configs_export.csv"'},
    )


@router.post("/csv/import")
async def api_import_sys_configs_csv(
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
    data = sys_config_service.import_sys_configs_from_csv(db, text, updated_by=me.id)
    log_action(
        db,
        tag="audit",
        action="sys_config.import_csv",
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
    page_size: int = Query(50, ge=1, le=500),
    keyword: str | None = Query(default=None, max_length=100),
    category: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    items, total = sys_config_service.list_configs(db, page, page_size, keyword, category)
    return ok({"items": [SysConfigOut.model_validate(c).model_dump() for c in items], "total": total, "page": page, "page_size": page_size})


@router.post("")
def api_create(
    data: SysConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    c = sys_config_service.create_config(db, data, updated_by=me.id)
    log_action(db, tag="audit", action="sys_config.create", user_id=me.id, username=me.username, ip=get_client_ip(request), remark=f"{c.category}.{c.code}")
    return ok(SysConfigOut.model_validate(c).model_dump(), msg="创建成功")


@router.put("/{cid}")
def api_update(
    cid: int,
    data: SysConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    c = sys_config_service.update_config(db, cid, data, updated_by=me.id)
    log_action(db, tag="audit", action="sys_config.update", user_id=me.id, username=me.username, ip=get_client_ip(request), remark=f"{c.category}.{c.code}")
    return ok(SysConfigOut.model_validate(c).model_dump(), msg="保存成功")


@router.delete("/{cid}")
def api_delete(
    cid: int,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    sys_config_service.delete_config(db, cid)
    log_action(
        db,
        tag="audit",
        action="sys_config.delete",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
        remark=f"ID {cid}",
    )
    return ok(msg="已删除")
