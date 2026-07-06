"""应用配置：基于 pydantic-settings 从环境变量/.env 加载"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.local_storage import (
    assert_upload_root_writable,
    ensure_upload_tree,
    log_storage_layout,
    resolve_upload_root,
    resolve_under_upload_root,
    validate_upload_root_config,
)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path:
    """只读资源根：开发为项目根；PyInstaller onefile 为 _MEIPASS。"""
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _runtime_root() -> Path:
    """可写数据根：开发为项目根；打包后为 exe 所在目录。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BUNDLE_ROOT = _bundle_root()
RUNTIME_ROOT = _runtime_root()
# 兼容旧代码：相对路径的数据库、上传目录等均以运行目录为准
PROJECT_ROOT = RUNTIME_ROOT


def _sqlite_data_path(url: str) -> Path | None:
    """解析 sqlite 相对 URL 到本地文件路径（用于创建父目录）。"""
    if not url.startswith("sqlite"):
        return None
    rest = url.removeprefix("sqlite:///")
    if not rest or rest.startswith("//"):
        return None
    if rest.startswith("/") or (len(rest) > 1 and rest[1] == ":"):
        return Path(rest.split("?", 1)[0])
    return (RUNTIME_ROOT / rest).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(RUNTIME_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    HOST: str = "0.0.0.0"
    PORT: int = 8808
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./data/lab_system.db"

    # Redis（可选；Docker Compose 默认 redis://redis:6379/0）
    REDIS_URL: str = ""
    WAIT_FOR_REDIS: bool = False
    REDIS_WAIT_TIMEOUT: int = Field(default=30, ge=1, le=300)

    UPLOAD_ROOT: str = "uploads"

    @field_validator("UPLOAD_ROOT")
    @classmethod
    def _validate_upload_root(cls, v: str) -> str:
        return validate_upload_root_config(v)

    VIDEO_MAX_UPLOAD_MB: int = Field(default=5120, ge=1, le=102400)
    VIDEO_CHUNK_SIZE_MB: int = Field(default=5, ge=1, le=50)
    # 允许未登录用户播放「公开」视频；关闭后所有播放均需登录
    VIDEO_ALLOW_ANONYMOUS_PLAY: bool = True
    # 未登录用户可见的评论条数（其余需登录查看）
    VIDEO_COMMENT_GUEST_PREVIEW: int = Field(default=2, ge=0, le=20)

    # 上传后自动转码为 MP4(H.264+AAC)；关闭则原样保存（MOV 等可能无法在线播放）
    VIDEO_TRANSCODE_ENABLED: bool = True
    FFMPEG_BIN: str = "ffmpeg"
    FFPROBE_BIN: str = "ffprobe"
    VIDEO_TRANSCODE_PRESET: str = "fast"
    VIDEO_TRANSCODE_CRF: int = Field(default=23, ge=18, le=32)
    VIDEO_TRANSCODE_TIMEOUT_SEC: int = Field(default=3600, ge=60, le=7200)

    SECRET_KEY: str = "app-platform-change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "admin2026"

    CORS_ORIGINS: str = "*"
    LOGIN_MAX_ATTEMPTS: int = 8
    LOGIN_WINDOW_SECONDS: int = 300
    LOGIN_LOCK_SECONDS: int = 600

    # ---------- 定时数据库备份 + SMTP 邮件（关闭则完全不调度）----------
    BACKUP_EMAIL_ENABLED: bool = False
    # 每天触发时刻（按 BACKUP_TIMEZONE 的本地时间）
    BACKUP_HOUR: int = Field(default=3, ge=0, le=23)
    BACKUP_MINUTE: int = Field(default=0, ge=0, le=59)
    BACKUP_TIMEZONE: str = "Asia/Shanghai"
    # mysqldump 可执行文件（需在 PATH 或写绝对路径）
    MYSQLDUMP_PATH: str = "mysqldump"
    # SMTP（留空则启用备份邮件时会在日志中报错并跳过发送）
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True
    # 465 等端口使用隐式 SSL 时设为 true（与 SMTP_USE_TLS 二选一常见组合：587+TLS 或 465+SSL）
    SMTP_USE_SSL: bool = False
    # 多个收件人用英文逗号或分号分隔
    BACKUP_EMAIL_TO: str = ""
    # 是否在发送后保留一份到本地目录（便于排查）
    BACKUP_KEEP_LOCAL_COPY: bool = False
    BACKUP_LOCAL_DIR: str = "uploads/db_backups"

    @property
    def backup_email_recipients(self) -> List[str]:
        raw = (self.BACKUP_EMAIL_TO or "").replace(";", ",")
        return [x.strip() for x in raw.split(",") if x.strip()]

    @property
    def is_mysql_database(self) -> bool:
        u = (self.DATABASE_URL or "").strip().lower()
        return u.startswith("mysql")

    @property
    def is_sqlite_database(self) -> bool:
        u = (self.DATABASE_URL or "").strip().lower()
        return u.startswith("sqlite")

    @property
    def redis_enabled(self) -> bool:
        return bool((self.REDIS_URL or "").strip())

    @property
    def project_root(self) -> Path:
        return RUNTIME_ROOT

    @property
    def bundle_root(self) -> Path:
        """静态页、打包进来的只读资源（如 web/）。"""
        return BUNDLE_ROOT

    @property
    def upload_root_path(self) -> Path:
        return resolve_upload_root(RUNTIME_ROOT, self.UPLOAD_ROOT)

    def resolve_upload_file(self, relative: str) -> Path:
        """解析相对路径为 UPLOAD_ROOT 下的本地绝对路径。"""
        return resolve_under_upload_root(self.upload_root_path, relative)

    @property
    def video_files_root_path(self) -> Path:
        return self.upload_root_path / "videos" / "files"

    @property
    def video_chunks_root_path(self) -> Path:
        return self.upload_root_path / "videos" / "chunks"

    @property
    def video_covers_root_path(self) -> Path:
        return self.upload_root_path / "videos" / "covers"

    @property
    def user_avatars_root_path(self) -> Path:
        return self.upload_root_path / "user_avatars"

    @property
    def site_branding_root_path(self) -> Path:
        return self.upload_root_path / "site_branding"

    @property
    def VIDEO_MAX_UPLOAD_BYTES(self) -> int:
        return int(self.VIDEO_MAX_UPLOAD_MB) * 1024 * 1024

    @property
    def VIDEO_CHUNK_SIZE_BYTES(self) -> int:
        return int(self.VIDEO_CHUNK_SIZE_MB) * 1024 * 1024

    @property
    def cors_origin_list(self) -> List[str]:
        if not self.CORS_ORIGINS or self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    def ensure_dirs(self) -> None:
        root = self.upload_root_path
        ensure_upload_tree(root)
        assert_upload_root_writable(root)
        if self.BACKUP_KEEP_LOCAL_COPY:
            lp = Path(self.BACKUP_LOCAL_DIR)
            if not lp.is_absolute():
                lp = RUNTIME_ROOT / lp
            lp.mkdir(parents=True, exist_ok=True)
        db_file = _sqlite_data_path(self.DATABASE_URL)
        if db_file is not None:
            db_file.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
