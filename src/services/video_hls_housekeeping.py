"""HLS 健康巡检：发现「没有切片 / 切片不完整」的 ready 视频并自动补切片。

存在的理由：HLS 生成失败只会打一条 warning（`prepare_for_web_playback` 的
try/except 吞掉），运维不翻日志就不知道有片子只有单码率 MP4 可播。巡检把
这件事变成可主动发现、可自动修复、可在接口里看到状态的事。

随应用启动周期运行；单次扫描有间隔与批量上限，避免和上传转码抢 IO。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.database import SessionLocal
from src.models.video import Video
from src.services import video_hls_service
from src.services.video_service import video_abs_path

logger = logging.getLogger(__name__)


def _playlist_uris(body: str) -> list[str]:
    """取出 playlist 里的媒体 URI（跳过 # 注释与 #EXT 标签行）。"""
    return [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _variant_usable(root: Path, rel: str) -> bool:
    """校验 master 指向的单个变体：playlist 在、init 段在、首尾分片在。"""
    # 变体 URI 可能是 stream_0/playlist.m3u8，也可能是相对更深的路径
    vp = (root / rel).resolve()
    if root.resolve() not in vp.parents:  # 防目录穿越
        return False
    if not vp.is_file():
        return False
    try:
        body = vp.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    parent = vp.parent
    # fMP4：init 段（#EXT-X-MAP）缺失则整条流无法解码
    for line in body.splitlines():
        if line.startswith("#EXT-X-MAP:URI="):
            uri = line.split('URI="', 1)[-1].split('"', 1)[0]
            if uri and not (parent / uri).is_file():
                return False
    segs = _playlist_uris(body)
    if not segs:
        return False
    # 全量校验太慢，抽查首尾：拷贝/清理中断通常整段缺失，而非丢中间一片
    for name in (segs[0], segs[-1]):
        if not (parent / name).is_file():
            return False
    return True


class HlsHousekeeper:
    """周期扫描缺失 HLS 的视频并补切片。"""

    def __init__(self, interval_sec: int = 900, batch: int = 3) -> None:
        self.interval_sec = max(60, interval_sec)
        self.batch = max(1, min(batch, 20))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at = 0.0
        self.last_result: dict = {}

    # ---- 生命周期 ----
    def start(self) -> None:
        if not settings.VIDEO_HLS_HOUSEKEEPING_ENABLED:
            logger.info("HLS 巡检未启用（VIDEO_HLS_HOUSEKEEPING_ENABLED=false）")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="hls-housekeeping", daemon=True)
        self._thread.start()
        logger.info("HLS 巡检已启动 interval=%ss batch=%d", self.interval_sec, self.batch)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:  # 巡检异常不能影响服务
                logger.warning("HLS 巡检失败: %s", exc)
            self._stop.wait(self.interval_sec)

    # ---- 扫描 ----
    def scan_once(self) -> dict:
        """扫一轮；返回统计（供状态接口展示）。"""
        self.last_run_at = time.time()
        result = {"checked": 0, "repaired": 0, "failed": 0, "pending": 0, "skipped": 0}
        db: Session = SessionLocal()
        try:
            videos = (
                db.query(Video)
                .filter(Video.status == "ready")
                .order_by(Video.id.desc())
                .limit(200)
                .all()
            )
            missing = [v for v in videos if not self._is_healthy(v)]
            result["pending"] = len(missing)
            for video in missing[: self.batch]:
                result["checked"] += 1
                path = video_abs_path(video)
                if not path.is_file():
                    result["skipped"] += 1
                    continue
                try:
                    video_hls_service.generate_hls(
                        path, video_hls_service.storage_key(video)
                    )
                    result["repaired"] += 1
                    logger.info("HLS 巡检补切片成功 video_id=%s", video.id)
                except Exception as exc:
                    result["failed"] += 1
                    logger.warning("HLS 巡检补切片失败 video_id=%s: %s", video.id, exc)
        finally:
            db.close()
        self.last_result = result
        return result

    @staticmethod
    def _is_healthy(video: Video) -> bool:
        """master 声明的每个变体都真实存在且有可用分片才算健康。

        只看「有没有 master」或「有没有任一 stream_* 目录」都不够：
        - 只检查 master → 切到一半失败的片子算成健康，点播放 404 在第一个分片；
        - 只检查任一变体 → 丢了一两个档位的片子也算健康，master 却还指向它们，
          自动档一切到那档就黑屏。所以必须拿 master 里的声明逐个对账。
        """
        root = video_hls_service.hls_dir(video_hls_service.storage_key(video))
        master = root / "master.m3u8"
        if not master.is_file():
            return False
        try:
            body = master.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        variants = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not variants:
            return False
        return all(_variant_usable(root, rel) for rel in variants)

    # ---- 状态 ----
    def status(self) -> dict:
        return {
            "enabled": settings.VIDEO_HLS_HOUSEKEEPING_ENABLED,
            "running": bool(self._thread and self._thread.is_alive()),
            "interval_sec": self.interval_sec,
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
        }


_housekeeper: HlsHousekeeper | None = None


def start_housekeeping() -> None:
    global _housekeeper
    if _housekeeper is None:
        _housekeeper = HlsHousekeeper(
            interval_sec=settings.VIDEO_HLS_HOUSEKEEPING_INTERVAL_SEC,
            batch=settings.VIDEO_HLS_HOUSEKEEPING_BATCH,
        )
    _housekeeper.start()


def stop_housekeeping() -> None:
    if _housekeeper:
        _housekeeper.stop()


def housekeeping_status() -> dict:
    if _housekeeper is None:
        return {"enabled": settings.VIDEO_HLS_HOUSEKEEPING_ENABLED, "running": False}
    return _housekeeper.status()


def scan_now() -> dict:
    """手动触发一次扫描（管理端用）。"""
    global _housekeeper
    if _housekeeper is None:
        _housekeeper = HlsHousekeeper(
            interval_sec=settings.VIDEO_HLS_HOUSEKEEPING_INTERVAL_SEC,
            batch=settings.VIDEO_HLS_HOUSEKEEPING_BATCH,
        )
    return _housekeeper.scan_once()


def hls_health_report(db: Session, limit: int = 50) -> dict:
    """不修复、只报告：当前有多少视频缺 HLS。"""
    videos = (
        db.query(Video).filter(Video.status == "ready").order_by(Video.id.desc()).limit(500).all()
    )
    unhealthy = [
        {"video_id": v.id, "title": v.title}
        for v in videos
        if not HlsHousekeeper._is_healthy(v)
    ]
    return {
        "checked": len(videos),
        "unhealthy": len(unhealthy),
        "items": unhealthy[: max(1, min(limit, 200))],
    }
