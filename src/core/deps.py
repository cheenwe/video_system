"""FastAPI 依赖注入"""
from __future__ import annotations

from typing import Optional
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.security import decode_access_token
from src.models.auth_revoked_token import AuthRevokedToken
from src.models.user import User


def extract_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    if authorization:
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return authorization.strip()
    qp = request.query_params.get("token")
    if qp:
        return qp.strip()
    return None


def get_optional_user(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> Optional[User]:
    token = extract_token(request, authorization)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("user_id")
    jti = payload.get("jti")
    if jti:
        revoked = db.query(AuthRevokedToken).filter(AuthRevokedToken.jti == str(jti)).first()
        if revoked:
            return None
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or user.disabled:
        return None
    request.state.current_user = user
    return user


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    token = extract_token(request, authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    user_id = payload.get("user_id")
    jti = payload.get("jti")
    if jti:
        revoked = db.query(AuthRevokedToken).filter(AuthRevokedToken.jti == str(jti)).first()
        if revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效凭证")
    user = db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    request.state.current_user = user
    return user


def is_admin(user: User) -> bool:
    return (user.role or "").lower() == "admin"


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def require_admin_for_delete(user: User = Depends(get_current_user)) -> User:
    """业务数据删除（客户、收样、检测记录、报告等）仅管理员。"""
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="删除操作需要管理员权限")
    return user


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


def get_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return str(rid)
    return ""
