"""FastAPI 应用入口"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from src.api.router import api_router
from src.api.seo import router as seo_router
from src.core.config import settings
from src.core.exceptions import register_exception_handlers
from src.core.init_db import init_database
from src.core.logging import logger, setup_logging
from src.core.local_storage import log_storage_layout
from src.core.redis_client import close_redis, ping_redis
from src.core.security_middleware import SecurityFilterMiddleware
from src.jobs.backup_scheduler import shutdown_backup_scheduler, start_backup_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("DEBUG" if settings.DEBUG else "INFO")
    settings.ensure_dirs()
    log_storage_layout(settings.upload_root_path, logger)
    init_database()
    if settings.redis_enabled:
        if settings.WAIT_FOR_REDIS:
            import time

            deadline = time.monotonic() + settings.REDIS_WAIT_TIMEOUT
            while time.monotonic() < deadline:
                if ping_redis():
                    break
                time.sleep(1)
            else:
                logger.error("Redis 在 %ss 内未就绪: %s", settings.REDIS_WAIT_TIMEOUT, settings.REDIS_URL)
        if ping_redis():
            logger.info("Redis 已连接: %s", settings.REDIS_URL)
        else:
            logger.warning("Redis 已配置但连接失败: %s", settings.REDIS_URL)
    logger.info(
        "应用启动完成。配置 HOST=%s PORT=%s（若用 uvicorn --host/--port，实际监听以命令行为准）",
        settings.HOST,
        settings.PORT,
    )
    start_backup_scheduler()
    yield
    shutdown_backup_scheduler()
    close_redis()
    logger.info("应用关闭")


def create_app() -> FastAPI:
    doc_kw = {}
    if not settings.DEBUG:
        doc_kw = {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(
        title="基础平台",
        version="1.0.0",
        description="用户、配置、日志、视频与运行环境管理",
        lifespan=lifespan,
        **doc_kw,
    )

    allow_all = settings.cors_origin_list == ["*"]
    app.add_middleware(SecurityFilterMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", rid)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # 保持兼容当前内联脚本，同时增加基本 CSP 约束
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        return response

    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(seo_router)

    web_dir = settings.bundle_root / "web"

    # 无同名 .html 时的路径别名（侧栏 href 与物理文件名不一致）
    _PAGE_ALIASES: dict[str, str] = {
        "video_system": "video_manage.html",
    }

    @app.get("/api/health", tags=["系统"])
    def health():
        payload: dict = {"success": 1, "msg": "ok"}
        if settings.redis_enabled:
            payload["redis"] = "ok" if ping_redis() else "down"
        return payload

    @app.get("/", include_in_schema=False)
    def root():
        target = web_dir / "index.html"
        if target.exists():
            return FileResponse(str(target))
        return JSONResponse({"success": 1, "msg": "lab_system api running"})

    @app.get("/{rest_of_path:path}", include_in_schema=False)
    def static_or_404(rest_of_path: str):
        # 优先静态资源
        if rest_of_path.startswith("api/"):
            raise HTTPException(status_code=404)
        if rest_of_path in ("robots.txt", "sitemap.xml"):
            raise HTTPException(status_code=404)
        alias_file = _PAGE_ALIASES.get(rest_of_path)
        if alias_file:
            alias_path = (web_dir / alias_file).resolve()
            if str(alias_path).startswith(str(web_dir.resolve())) and alias_path.is_file():
                return FileResponse(str(alias_path))
        full = (web_dir / rest_of_path).resolve()
        base = web_dir.resolve()
        if not str(full).startswith(str(base)):
            raise HTTPException(status_code=404)
        if full.is_file():
            return FileResponse(str(full))
        if rest_of_path and not Path(rest_of_path).suffix:
            html_file = (web_dir / f"{rest_of_path}.html").resolve()
            if str(html_file).startswith(str(base)) and html_file.is_file():
                return FileResponse(str(html_file))
        if full.is_dir():
            idx = full / "index.html"
            if idx.exists():
                return FileResponse(str(idx))
        # 单页应用回退（如直接访问 /clients）
        idx = web_dir / "index.html"
        if rest_of_path and not Path(rest_of_path).suffix and idx.exists():
            return FileResponse(str(idx))
        raise HTTPException(status_code=404)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
