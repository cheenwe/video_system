#!/usr/bin/env python3
"""为已有 MP4 视频补生成 HLS 切片（无需重建 Docker 镜像）。"""
from __future__ import annotations

import argparse
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser(description="为已有视频补生成 HLS")
    parser.add_argument("--video-id", type=int, help="仅处理指定视频 ID")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数，0 表示全部")
    args = parser.parse_args()

    if not settings.VIDEO_HLS_ENABLED:
        print("VIDEO_HLS_ENABLED=false，请先开启 HLS")
        return 1

    db = SessionLocal()
    try:
        q = db.query(Video).filter(Video.status == "ready").order_by(Video.id.desc())
        if args.video_id:
            q = q.filter(Video.id == args.video_id)
        videos = q.all()
        if args.limit and args.limit > 0:
            videos = videos[: args.limit]

        ok = fail = skip = 0
        for v in videos:
            key = video_hls_service.storage_key(v)
            if video_hls_service.master_playlist_path(key).is_file():
                skip += 1
                print(f"[skip] #{v.id} {v.title}")
                continue
            path = video_abs_path(v)
            if not path.is_file():
                fail += 1
                print(f"[fail] #{v.id} 文件不存在: {path}")
                continue
            try:
                probe = probe_media(path)
                video_hls_service.generate_hls(path, key, probe)
                ok += 1
                print(f"[ok]   #{v.id} {v.title}")
            except Exception as exc:
                fail += 1
                print(f"[fail] #{v.id} {exc}")
        print(f"完成: ok={ok} skip={skip} fail={fail}")
        return 0 if fail == 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
