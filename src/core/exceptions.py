"""统一异常与响应"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class BizError(Exception):
    """业务异常"""

    def __init__(self, msg: str, code: int = 400, data: Any = None):
        self.msg = msg
        self.code = code
        self.data = data
        super().__init__(msg)


def ok(data: Any = None, msg: str = "ok") -> dict:
    return {"success": 1, "msg": msg, "data": data}


def fail(msg: str, code: int = 400, data: Any = None) -> dict:
    return {"success": 0, "msg": msg, "code": code, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz(_: Request, exc: BizError):
        return JSONResponse(status_code=200, content=fail(exc.msg, exc.code, exc.data))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []))
        msg = f"参数错误: {loc} {first.get('msg', '')}".strip()
        return JSONResponse(status_code=200, content=fail(msg, 422))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return JSONResponse(status_code=401, content=fail(exc.detail or "未登录或登录已过期", 401))
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return JSONResponse(status_code=403, content=fail(exc.detail or "无权限", 403))
        return JSONResponse(status_code=exc.status_code, content=fail(exc.detail or "请求失败", exc.status_code))

    @app.exception_handler(Exception)
    async def _any(_: Request, exc: Exception):
        logger.exception("未处理异常")
        from src.core.config import settings

        if settings.DEBUG:
            msg = f"服务器内部错误: {exc}"
        else:
            msg = "服务器内部错误，请稍后重试"
        return JSONResponse(status_code=500, content=fail(msg, 500))
