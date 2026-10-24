#!/usr/bin/env python3
"""为已有 MP4 视频补生成 HLS 切片（存量片接入多码率阶梯）。

对应弱网优化计划 P1.1：对没有 `master.m3u8` 的 ready 视频批量 `generate_hls`，
失败条目进入重试队列再跑若干轮，并写入日志，便于排查「为什么这条没切」。

用法：
    python scripts/backfill_hls.py                 # 全量补切片
    python scripts/backfill_hls.py --limit 20      # 只处理 20 条
    python scripts/backfill_hls.py --video-id 42   # 只处理指定视频
    python scripts/backfill_hls.py --dry-run       # 只列出待处理，不执行
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import settings
from src.core.database import SessionLocal
from src.models.video import Video
from src.services import video_hls_service
from src.services.video_service import video_abs_path
from src.services.video_transcode_service import probe_media

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_hls")


def pending_videos(db, video_id: int | None) -> list[Video]:
    """没有 master.m3u8 的 ready 视频（新上传已带 HLS 的不在列表内）。"""
    q = db.query(Video).filter(Video.status == "ready").order_by(Video.id.desc())
    if video_id:
        q = q.filter(Video.id == video_id)
    out: list[Video] = []
    for v in q.all():
        if video_hls_service.master_playlist_path(video_hls_service.storage_key(v)).is_file():
            continue
        out.append(v)
    return out


def process(db, video: Video) -> None:
    path = video_abs_path(video)
    if not path.is_file():
        raise FileNotFoundError(f"视频文件不存在: {path}")
    probe = probe_media(path)
    video_hls_service.generate_hls(path, video_hls_service.storage_key(video), probe)


def main() -> int:
    parser = argparse.ArgumentParser(description="为已有视频补生成 HLS")
    parser.add_argument("--video-id", type=int, help="仅处理指定视频 ID")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数，0 表示全部")
    parser.add_argument("--retries", type=int, default=2, help="失败条目的额外重试轮数（默认 2）")
    parser.add_argument("--dry-run", action="store_true", help="只列出待处理视频，不执行")
    args = parser.parse_args()

    if not settings.VIDEO_HLS_ENABLED:
        print("VIDEO_HLS_ENABLED=false，请先开启 HLS")
        return 1

    db = SessionLocal()
    try:
        videos = pending_videos(db, args.video_id)
        if args.limit and args.limit > 0:
            videos = videos[: args.limit]
        if not videos:
            print("没有需要补切片的视频")
            return 0

        if args.dry_run:
            for v in videos:
                print(f"[todo] #{v.id} {v.title}")
            print(f"共 {len(videos)} 条待处理")
            return 0

        ok = 0
        queue = list(videos)
        for attempt in range(max(0, args.retries) + 1):
            if not queue:
                break
            if attempt:
                logger.info("第 %d 轮重试 %d 条失败项", attempt, len(queue))
                time.sleep(2 * attempt)  # 退避，避免连续打满磁盘/CPU
            retry: list[Video] = []
            for v in queue:
                try:
                    process(db, v)
                    ok += 1
                    print(f"[ok]   #{v.id} {v.title}")
                except Exception as exc:
                    logger.warning("#%s %s 切片失败: %s", v.id, v.title, exc)
                    retry.append(v)
            queue = retry

        fail = len(queue)
        print(f"完成: ok={ok} fail={fail}（共尝试 {len(videos)} 条）")
        return 0 if fail == 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
