"""认证接口"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import get_db
from src.core.deps import extract_token, get_client_ip, get_current_user, get_request_id
from src.core.exceptions import BizError, ok
from src.models.auth_revoked_token import AuthRevokedToken
from src.models.user import User
from src.schemas.auth import LoginRequest
from src.schemas.password import ChangePasswordRequest
from src.schemas.user import UserSelfProfileUpdate
from src.services.auth_service import change_password, login
from src.services.log_service import log_action
from src.services import user_avatar_service, user_service


def _user_client_dict(user: User) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "is_admin": (user.role or "user").lower() == "admin",
        "real_name": user.real_name,
        "timezone": getattr(user, "timezone", None) or "UTC",
        "avatar_url": user_avatar_service.avatar_url(user),
    }

router = APIRouter(prefix="/api/auth", tags=["认证"])
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_login_lock_until: dict[str, float] = {}


def _login_key(username: str, ip: str) -> str:
    return f"{(username or '').strip().lower()}@{ip or '-'}"


def _assert_login_allowed(username: str, ip: str) -> None:
    now = time.time()
    key = _login_key(username, ip)
    locked_until = _login_lock_until.get(key, 0.0)
    if locked_until > now:
        wait = int(locked_until - now)
        raise BizError(f"登录失败过多，请 {wait} 秒后重试", 429)


def _record_login_failure(username: str, ip: str, db: Session | None = None) -> None:
    now = time.time()
    key = _login_key(username, ip)
    q = _login_failures[key]
    q.append(now)
    window = max(30, settings.LOGIN_WINDOW_SECONDS)
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= max(3, settings.LOGIN_MAX_ATTEMPTS):
        _login_lock_until[key] = now + max(60, settings.LOGIN_LOCK_SECONDS)
        q.clear()
        if db is not None:
            lock_sec = max(60, settings.LOGIN_LOCK_SECONDS)
            log_action(
                db,
                tag="audit",
                result="success",
                action="auth.login_rate_limited",
                username=(username or "").strip() or None,
                ip=ip,
                remark=f"登录失败过多，{lock_sec}s 内禁止该账号在此 IP 继续尝试",
            )


def _clear_login_failure(username: str, ip: str) -> None:
    key = _login_key(username, ip)
    _login_failures.pop(key, None)
    _login_lock_until.pop(key, None)


@router.post("/login")
def api_login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    _assert_login_allowed(data.username, ip)
    try:
        user, token = login(db, data.username, data.password)
    except BizError as e:
        _record_login_failure(data.username, ip, db)
        log_action(
            db,
            tag="login",
            result="failed",
            action="login",
            username=data.username,
            ip=ip,
            request_id=get_request_id(request),
            remark=e.msg,
        )
        raise
    _clear_login_failure(data.username, ip)
    log_action(
        db,
        tag="login",
        result="success",
        action="login",
        user_id=user.id,
        username=user.username,
        ip=ip,
        request_id=get_request_id(request),
    )
    return ok(
        data={
            "token": token,
            **_user_client_dict(user),
        },
        msg="登录成功",
    )


@router.get("/me")
def api_me(user: User = Depends(get_current_user)):
    return ok(data=_user_client_dict(user))


@router.get("/timezones")
def api_timezones(_user: User = Depends(get_current_user)):
    """IANA 时区标识列表（与后端 ZoneInfo 一致），供前端可搜索下拉使用。"""
    from zoneinfo import available_timezones

    items = sorted(available_timezones())
    return ok(data={"items": items})


@router.put("/profile")
def api_update_profile(
    data: UserSelfProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    u = user_service.update_self_profile(db, user, data)
    log_action(
        db,
        tag="operation",
        action="auth.profile.update",
        user_id=u.id,
        username=u.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
        remark="个人信息",
    )
    return ok(data=_user_client_dict(u), msg="已保存")


@router.post("/avatar")
async def api_upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    u = await user_avatar_service.save_avatar(db, user, file)
    log_action(
        db,
        tag="operation",
        action="auth.avatar.upload",
        user_id=u.id,
        username=u.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
    )
    return ok(data=_user_client_dict(u), msg="头像已更新")


@router.delete("/avatar")
def api_delete_avatar(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    u = user_avatar_service.remove_avatar(db, user)
    log_action(
        db,
        tag="operation",
        action="auth.avatar.delete",
        user_id=u.id,
        username=u.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
    )
    return ok(data=_user_client_dict(u), msg="已恢复默认头像")


@router.get("/avatars/{user_id}")
def api_get_avatar(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise BizError("用户不存在", 404)
    path = user_avatar_service.avatar_abs_path(user)
    if not path:
        raise BizError("头像不存在", 404)
    return FileResponse(
        str(path),
        media_type=user_avatar_service.avatar_media_type(path),
        filename=path.name,
        stat_result=path.stat(),
    )


@router.post("/logout")
def api_logout(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = extract_token(request, authorization)
    if token:
        from src.core.security import decode_access_token

        payload = decode_access_token(token) or {}
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and not db.query(AuthRevokedToken).filter(AuthRevokedToken.jti == str(jti)).first():
            exp_dt = None
            try:
                if exp:
                    exp_dt = datetime.fromtimestamp(int(exp), tz=timezone.utc).replace(tzinfo=None)
            except Exception:
                exp_dt = None
            db.add(AuthRevokedToken(jti=str(jti), expires_at=exp_dt))
            db.commit()
    log_action(
        db,
        tag="login",
        result="success",
        action="logout",
        user_id=user.id,
        username=user.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
    )
    return ok(msg="已退出")


@router.post("/change-password")
def api_change_password(
    data: ChangePasswordRequest,
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_password(db, user, data.old_password, data.new_password)
    token = extract_token(request, authorization)
    if token:
        from src.core.security import decode_access_token

        payload = decode_access_token(token) or {}
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and not db.query(AuthRevokedToken).filter(AuthRevokedToken.jti == str(jti)).first():
            exp_dt = None
            try:
                if exp:
                    exp_dt = datetime.fromtimestamp(int(exp), tz=timezone.utc).replace(tzinfo=None)
            except Exception:
                exp_dt = None
            db.add(AuthRevokedToken(jti=str(jti), expires_at=exp_dt))
            db.commit()
    log_action(
        db,
        tag="audit",
        result="success",
        action="auth.change_password",
        user_id=user.id,
        username=user.username,
        ip=get_client_ip(request),
        request_id=get_request_id(request),
    )
    return ok(msg="密码修改成功，请重新登录")
