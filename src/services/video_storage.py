"""视频存储抽象：本地磁盘（默认）或 S3 兼容对象存储。

弱网优化计划 P2-1：把 HLS 分片的字节下发转移到 OSS/CDN，减轻源站压力。

**鉴权不旁路**：对象存储只承担「字节下发」。平台仍在 `/api/videos/{id}/hls/...`
做完整鉴权，通过后 302 到一个**短时效**预签名 URL。因此：
- 私有/需登录视频不会被未授权访问（URL 本身短时效，且只有鉴权通过才发）；
- 应用侧无需把 token 透传到 OSS。

上传侧：HLS 生成后把整个目录同步到 OSS（后台线程，失败只记日志，
不影响本地播放，下次生成会重试）。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from src.core.config import settings
from src.core.s3_signer import S3Config, presign_get, presign_put

logger = logging.getLogger(__name__)

_MIME_BY_EXT = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".m4s": "video/iso.segment",
    ".mp4": "video/mp4",
}


@dataclass(frozen=True)
class ResolvedAsset:
    """一个 HLS 资源的寻址结果。

    - redirect_url 非空：让客户端 302 到该地址（OSS/CDN）
    - 为空：由调用方按本地文件响应
    """

    local_path: Path | None
    redirect_url: str
    media_type: str


def object_key(upload_id: str, asset_path: str) -> str:
    prefix = (settings.S3_PREFIX or "video-hls").strip("/")
    return f"{prefix}/{upload_id}/{asset_path.lstrip('/')}"


def s3_config() -> S3Config | None:
    """配置完整时返回 S3Config，否则 None（调用方回退本地）。"""
    if (settings.VIDEO_STORAGE_BACKEND or "local").lower() != "s3":
        return None
    if not (settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY):
        logger.warning("VIDEO_STORAGE_BACKEND=s3 但 S3_* 配置不完整，回退本地存储")
        return None
    return S3Config(
        endpoint=settings.S3_ENDPOINT,
        bucket=settings.S3_BUCKET,
        region=settings.S3_REGION or "us-east-1",
        access_key_id=settings.S3_ACCESS_KEY_ID,
        secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        cdn_base_url=settings.VIDEO_CDN_BASE_URL or "",
        path_style=settings.S3_PATH_STYLE,
    )


def media_type_for(path: Path) -> str:
    return _MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")


def resolve_asset(upload_id: str, asset_path: str, local: Path) -> ResolvedAsset:
    """决定这个 HLS 资源怎么下发。

    本地后端：始终返回本地路径。
    S3 后端：对象存在则给预签名 URL；对象缺失（尚未同步）时退回本地，
    避免「上传到 OSS 失败」导致视频不可播。
    """
    cfg = s3_config()
    if cfg is None:
        return ResolvedAsset(local_path=local, redirect_url="", media_type=media_type_for(local))
    key = object_key(upload_id, asset_path)
    try:
        url = presign_get(cfg, key, expires_in=settings.VIDEO_SIGNED_URL_TTL_SEC)
    except Exception as exc:  # 配置/时钟异常不应让播放挂掉
        logger.warning("预签名失败，回退本地下发 %s: %s", key, exc)
        return ResolvedAsset(local_path=local, redirect_url="", media_type=media_type_for(local))
    return ResolvedAsset(local_path=None, redirect_url=url, media_type=media_type_for(local))


# ---------- 上传到对象存储 ----------

_upload_lock = threading.Lock()
_uploaded: set[str] = set()


def sync_hls_to_storage(upload_id: str, hls_root: Path) -> int:
    """把 HLS 目录同步到对象存储；返回上传文件数。

    已上传过（同 key 同尺寸）的跳过。失败抛给调用方记录，
    但不影响本地播放（下次生成会重试）。
    """
    cfg = s3_config()
    if cfg is None:
        return 0
    import urllib.request

    files = [p for p in hls_root.rglob("*") if p.is_file()]
    uploaded = 0
    for path in files:
        rel = path.relative_to(hls_root).as_posix()
        key = object_key(upload_id, rel)
        size = path.stat().st_size
        marker = f"{key}:{size}"
        with _upload_lock:
            if marker in _uploaded:
                continue
        url = presign_put(cfg, key, expires_in=900)
        data = path.read_bytes()
        req = urllib.request.Request(url, data=data, method="PUT")
        req.add_header("Content-Type", media_type_for(path))
        req.add_header("Content-Length", str(size))
        # 与签名时的 payload hash 保持一致，缺了它 S3 会拒绝
        req.add_header("x-amz-content-sha256", "UNSIGNED-PAYLOAD")
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            if resp.status not in (200, 204):
                raise OSError(f"上传 {key} 返回 {resp.status}")
        with _upload_lock:
            _uploaded.add(marker)
        uploaded += 1
    logger.info("HLS 已同步到对象存储 upload_id=%s files=%d", upload_id, uploaded)
    return uploaded


def sync_hls_async(upload_id: str, hls_root: Path) -> None:
    """后台同步；失败只记日志（本地播放不受影响，下次生成会重试）。"""
    if s3_config() is None:
        return

    def _run() -> None:
        try:
            sync_hls_to_storage(upload_id, hls_root)
        except Exception as exc:
            logger.warning("HLS 同步对象存储失败 upload_id=%s: %s", upload_id, exc)

    threading.Thread(target=_run, name=f"hls-sync-{upload_id[:8]}", daemon=True).start()
