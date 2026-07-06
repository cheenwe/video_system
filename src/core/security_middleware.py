"""基础 HTTP 请求安全中间件"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.core.input_security import contains_sql_injection_probe, strip_control_chars

MAX_QUERY_LEN = 4096
MAX_PATH_LEN = 2048


class SecurityFilterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if len(path) > MAX_PATH_LEN or "\x00" in path:
            return JSONResponse(status_code=400, content={"success": 0, "msg": "非法请求路径", "code": 400})

        query = str(request.url.query or "")
        if len(query) > MAX_QUERY_LEN or "\x00" in query:
            return JSONResponse(status_code=400, content={"success": 0, "msg": "非法查询参数", "code": 400})

        for key, value in request.query_params.multi_items():
            if value is None:
                continue
            v = strip_control_chars(str(value))
            if contains_sql_injection_probe(v):
                return JSONResponse(
                    status_code=400,
                    content={"success": 0, "msg": "查询参数包含非法内容", "code": 400},
                )

        return await call_next(request)
