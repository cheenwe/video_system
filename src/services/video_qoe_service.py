"""播放质量（QoE）采集与汇总。

前端在「首次可播放 / 回退 / 离页」三个节点上报一次，服务端落库并提供
汇总报表，用来验证弱网优化是否真的有效（TTFF、卡顿次数、档位分布、
回退率）。没有这层闭环，调参就只能靠感觉。
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BizError
from src.models.video import Video, VideoQoEEvent

# 每个视频的上报最小间隔（秒）：同一会话重复打点只保留关键节点
_MIN_INTERVAL_SEC = 30
_last_report: dict[int, float] = {}


def record_event(
    db: Session,
    video: Video,
    *,
    ttff_ms: int,
    waiting_count: int,
    waiting_ms: int,
    level: int,
    auto_level: int,
    manual: bool,
    fallback_reason: str,
    downgrades: int,
    sw_cached: bool,
    elapsed_ms: int,
) -> None:
    """写入一条 QoE 事件；过于频繁的重复上报直接丢弃。"""
    now = time.monotonic()
    last = _last_report.get(video.id, 0.0)
    if now - last < _MIN_INTERVAL_SEC and not fallback_reason:
        return
    _last_report[video.id] = now

    db.add(
        VideoQoEEvent(
            video_id=video.id,
            ttff_ms=max(0, int(ttff_ms)),
            waiting_count=max(0, int(waiting_count)),
            waiting_ms=max(0, int(waiting_ms)),
            level=int(level),
            auto_level=int(auto_level),
            manual=1 if manual else 0,
            fallback_reason=(fallback_reason or "")[:120],
            downgrades=max(0, int(downgrades)),
            sw_cached=1 if sw_cached else 0,
            elapsed_ms=max(0, int(elapsed_ms)),
        )
    )
    db.commit()


def summary(db: Session, days: int = 7, video_id: int | None = None) -> dict:
    """汇总最近 N 天的播放质量指标。"""
    # 库里 created_at 由 SQLite 的 func.now() 写入，是 UTC 的 naive 值；
    # 这里必须同样取 UTC 再去掉 tzinfo，否则比较口径不一致会整段查空。
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 90)))
    q = db.query(VideoQoEEvent).filter(VideoQoEEvent.created_at >= since)
    if video_id:
        q = q.filter(VideoQoEEvent.video_id == video_id)
    rows = q.all()

    total = len(rows)
    if total == 0:
        return {
            "window_days": days,
            "sessions": 0,
            "ttff_ms_avg": 0,
            "ttff_ms_p95": 0,
            "waiting_total": 0,
            "waiting_ms_avg": 0,
            "fallback_rate": 0.0,
            "fallback_reasons": {},
            "level_distribution": {},
            "sw_cache_hit_rate": 0.0,
        }

    ttff = sorted(r.ttff_ms for r in rows if r.ttff_ms > 0)
    waiting_counts = [r.waiting_count for r in rows]
    waiting_ms = [r.waiting_ms for r in rows]
    fallbacks = [r for r in rows if r.fallback_reason]
    sw_hits = sum(1 for r in rows if r.sw_cached)

    reasons: dict[str, int] = defaultdict(int)
    for r in fallbacks:
        # 归并细节（如 "HLS 错误:xxx"）到大类，避免报表被长尾撑爆
        key = r.fallback_reason.split(":", 1)[0].strip() or "unknown"
        reasons[key] += 1

    levels: dict[str, int] = defaultdict(int)
    for r in rows:
        levels["自动" if r.manual == 0 else f"手动 L{r.level}"] += 1

    p95_index = min(len(ttff) - 1, int(len(ttff) * 0.95)) if ttff else 0
    return {
        "window_days": days,
        "sessions": total,
        "ttff_ms_avg": int(sum(ttff) / len(ttff)) if ttff else 0,
        "ttff_ms_p95": ttff[p95_index] if ttff else 0,
        "waiting_total": sum(waiting_counts),
        "waiting_ms_avg": int(sum(waiting_ms) / len(waiting_ms)),
        "fallback_rate": round(len(fallbacks) / total, 4),
        "fallback_reasons": dict(reasons),
        "level_distribution": dict(levels),
        "sw_cache_hit_rate": round(sw_hits / total, 4),
    }


def per_video_summary(db: Session, days: int = 7, limit: int = 20) -> list[dict]:
    """按视频汇总，便于定位「哪条片卡得多」。"""
    # 库里 created_at 由 SQLite 的 func.now() 写入，是 UTC 的 naive 值；
    # 这里必须同样取 UTC 再去掉 tzinfo，否则比较口径不一致会整段查空。
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 90)))
    rows = (
        db.query(
            VideoQoEEvent.video_id,
            func.count(VideoQoEEvent.id).label("sessions"),
            func.avg(VideoQoEEvent.ttff_ms).label("ttff"),
            func.sum(VideoQoEEvent.waiting_count).label("waiting"),
            func.sum(case((VideoQoEEvent.fallback_reason != "", 1), else_=0)).label("fallbacks"),
        )
        .filter(VideoQoEEvent.created_at >= since)
        .group_by(VideoQoEEvent.video_id)
        .order_by(func.count(VideoQoEEvent.id).desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    titles = {
        v.id: v.title
        for v in db.query(Video).filter(Video.id.in_([r.video_id for r in rows])).all()
    } if rows else {}
    return [
        {
            "video_id": r.video_id,
            "title": titles.get(r.video_id, f"#{r.video_id}"),
            "sessions": int(r.sessions or 0),
            "ttff_ms_avg": int(r.ttff or 0),
            "waiting_total": int(r.waiting or 0),
            "fallbacks": int(r.fallbacks or 0),
        }
        for r in rows
    ]


def assert_enabled() -> None:
    if not settings.VIDEO_QOE_ENABLED:
        raise BizError("播放质量采集未启用", 404)
