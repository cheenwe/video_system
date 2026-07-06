"""运行目录 .env 的查看与维护（仅管理员）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.config import Settings, get_settings
from src.core.deps import get_client_ip, get_request_id, require_admin
from src.core.dotenv_io import parse_dotenv, serialize_dotenv
from src.core.exceptions import BizError, ok
from src.models.user import User
from src.schemas.runtime_env import RuntimeEnvItem, RuntimeEnvListOut, RuntimeEnvPutBody
from src.services import runtime_env_service
from src.services.db_backup_email import run_backup_and_email
from src.services.log_service import log_action
from src.services.server_metrics_service import collect_server_metrics

router = APIRouter(prefix="/api/runtime-env", tags=["运行环境"])


@router.get("")
def api_runtime_env_list(_: User = Depends(require_admin)):
    raw_items, path = runtime_env_service.build_items()
    items = [RuntimeEnvItem(**x) for x in raw_items]
    out = RuntimeEnvListOut(
        items=items,
        path=path,
        full_example_env=runtime_env_service.full_example_env_text(),
    )
    return ok(out.model_dump())


@router.put("")
def api_runtime_env_put(
    body: RuntimeEnvPutBody,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    runtime_env_service.apply_client_dotenv(body.data)
    log_action(
        db,
        tag="audit",
        action="runtime_env.update",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
        remark=".env 已更新",
    )
    return ok(msg="已保存，部分项需重启进程后生效")


@router.get("/export")
def api_runtime_env_export(_: User = Depends(require_admin)):
    merged = runtime_env_service.merge_for_write({})
    fields = Settings.model_fields
    known_upper = {k.upper() for k in fields}
    key_order = [k.upper() for k in fields] + sorted(k for k in merged if k not in known_upper)
    body = serialize_dotenv(merged, key_order)
    return Response(
        content=body.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="lab_system.env"'},
    )


@router.post("/import")
async def api_runtime_env_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
):
    raw = await file.read()
    if not raw:
        raise BizError("文件为空")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise BizError("文件须为 UTF-8 编码的 .env 文本") from e
    data = parse_dotenv(text)
    runtime_env_service.apply_client_dotenv(dict(data))
    log_action(
        db,
        tag="audit",
        action="runtime_env.import_file",
        user_id=me.id,
        username=me.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
        remark=file.filename or "",
    )
    return ok(msg="导入并保存成功，部分项需重启进程后生效")


@router.get("/server-metrics")
def api_server_metrics(_: User = Depends(require_admin)):
    """当前进程所在主机的 CPU / 内存 / 磁盘概览（管理员）。"""
    return ok(collect_server_metrics())


@router.post("/backup-email/run")
def api_backup_email_run(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_admin),
    force: bool = Query(False, description="为 True 时忽略 BACKUP_EMAIL_ENABLED=false，仍执行备份并发信（仅调试用）"),
):
    """
    立即执行一次数据库备份并发送邮件（与定时任务逻辑一致），结果写入 sys_logs（action=db_backup.email）。
    """
    s = get_settings()
    try:
        out = run_backup_and_email(
            s,
            db=db,
            force=force,
            log_user_id=me.id,
            log_username=me.username,
            log_ip=get_client_ip(request),
            log_request_id=get_request_id(request),
        )
        if out.get("skipped"):
            return ok(out, msg="未执行备份：" + (out.get("skipped") or ""))
        return ok(out, msg="备份邮件已发送")
    except Exception as e:
        raise BizError(str(e)) from e
