"""本地文件存储：路径解析、目录初始化与写入校验（视频/头像/品牌资源等均落盘到 UPLOAD_ROOT）"""
from __future__ import annotations

import os
from pathlib import Path

from src.core.exceptions import BizError

# 相对 UPLOAD_ROOT 的子目录（启动时自动创建）
UPLOAD_SUBDIRS = (
    "videos/files",
    "videos/chunks",
    "videos/covers",
    "videos/covers/pending",
    "user_avatars",
    "site_branding",
    "db_backups",
)


def validate_upload_root_config(raw: str) -> str:
    """UPLOAD_ROOT 必须是本地目录，禁止 URL / 空值。"""
    s = (raw or "").strip()
    if not s:
        raise ValueError("UPLOAD_ROOT 不能为空")
    lower = s.lower()
    if "://" in lower or lower.startswith("\\\\"):
        raise ValueError("UPLOAD_ROOT 须为本地文件夹路径，不支持 http(s):// 或对象存储 URL")
    return s


def resolve_upload_root(runtime_root: Path, upload_root: str) -> Path:
    p = Path(upload_root)
    if not p.is_absolute():
        p = runtime_root / p
    return p.resolve()


def ensure_upload_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for sub in UPLOAD_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)


def assert_upload_root_writable(root: Path) -> None:
    if not root.is_dir():
        raise RuntimeError(f"上传根目录不存在: {root}")
    test = root / ".write_test"
    try:
        test.write_bytes(b"ok")
        test.unlink(missing_ok=True)
    except OSError as e:
        raise RuntimeError(f"上传根目录不可写: {root}") from e


def resolve_under_upload_root(root: Path, relative: str) -> Path:
    """将数据库中的相对路径解析为 UPLOAD_ROOT 下的绝对路径，禁止 .. 逃逸。"""
    if not relative or not str(relative).strip():
        raise BizError("文件路径无效", 400)
    rel = str(relative).replace("\\", "/").lstrip("/")
    parts = Path(rel).parts
    if ".." in parts:
        raise BizError("非法文件路径", 400)
    root_resolved = root.resolve()
    full = (root_resolved / rel).resolve()
    try:
        full.relative_to(root_resolved)
    except ValueError:
        raise BizError("非法文件路径", 400) from None
    return full


def safe_filename(name: str) -> str:
    """品牌资源等仅允许单层文件名。"""
    base = Path(name).name
    if not base or base in {".", ".."} or "/" in name or "\\" in name:
        raise BizError("非法文件名", 400)
    return base


def log_storage_layout(root: Path, logger) -> None:
    logger.info("本地文件存储根目录: %s", root)
    for sub in UPLOAD_SUBDIRS:
        p = root / sub
        logger.info("  └─ %s (%s)", sub, "可写" if os.access(p, os.W_OK) else "不可写")
