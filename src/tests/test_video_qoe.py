"""QoE 采集与汇总的单元测试。

重点覆盖两类容易静默出错的地方：
1. 上报体字段命名（JS camelCase / Python snake_case）必须都能解析，否则
   pydantic 会安静地忽略未知字段，落库成一条全 0 记录，报表直接失真；
2. 节流规则：同一视频 30s 内重复打点丢弃，但带降级原因的必须放行。
"""
from datetime import datetime, timedelta

from src.schemas.video import VideoQoEBody


def _camel():
    return {
        "ttffMs": 820,
        "waitingCount": 2,
        "waitingMs": 1500,
        "level": 2,
        "autoLevel": 3,
        "manual": True,
        "fallbackReason": "frag-load-error",
        "downgrades": 1,
        "swCached": True,
        "elapsedMs": 45000,
    }


def _snake():
    return {
        "ttff_ms": 820,
        "waiting_count": 2,
        "waiting_ms": 1500,
        "level": 2,
        "auto_level": 3,
        "manual": True,
        "fallback_reason": "frag-load-error",
        "downgrades": 1,
        "sw_cached": True,
        "elapsed_ms": 45000,
    }


def test_body_accepts_camel_case():
    b = VideoQoEBody(**_camel())
    assert (b.ttff_ms, b.waiting_count, b.waiting_ms) == (820, 2, 1500)
    assert (b.level, b.auto_level, b.manual) == (2, 3, True)
    assert (b.fallback_reason, b.downgrades, b.sw_cached, b.elapsed_ms) == (
        "frag-load-error", 1, True, 45000,
    )


def test_body_accepts_snake_case():
    b = VideoQoEBody(**_snake())
    assert b.ttff_ms == 820
    assert b.auto_level == 3
    assert b.sw_cached is True
    assert b.fallback_reason == "frag-load-error"


def test_body_defaults_are_explicit_absent_markers():
    """空体应得到「未知」哨兵值而不是 0，报表才能区分「没数据」和「真的很快」。"""
    b = VideoQoEBody()
    assert b.level == -1
    assert b.auto_level == -1
    assert b.manual is False
    assert b.ttff_ms == 0


def test_body_rejects_out_of_range():
    from pydantic import ValidationError

    bad = _camel()
    bad["ttffMs"] = 10 ** 7  # > 600_000
    try:
        VideoQoEBody(**bad)
    except ValidationError:
        return
    raise AssertionError("越界的 ttffMs 应被拒绝")


def test_summary_math_on_empty_and_populated():
    """汇总口径：TTFF 只统计 >0 的样本，p95 用排序近似，降级率按会话数。"""
    from src.services import video_qoe_service as svc

    class _Row:
        def __init__(self, ttff, waiting_count, waiting_ms, reason, sw, manual, level):
            self.ttff_ms = ttff
            self.waiting_count = waiting_count
            self.waiting_ms = waiting_ms
            self.fallback_reason = reason
            self.sw_cached = sw
            self.manual = manual
            self.level = level

    class _DB:
        def __init__(self, rows):
            self._rows = rows

        def query(self, *_a, **_k):
            return self

        def filter(self, *_a, **_k):
            return self

        def all(self):
            return self._rows

    empty = svc.summary(_DB([]), days=7)
    assert empty["sessions"] == 0
    assert empty["level_distribution"] == {}

    rows = [
        _Row(800, 1, 500, "", 1, 0, 2),
        _Row(0, 0, 0, "", 0, 0, 2),          # ttff 缺失，不计入均值
        _Row(2400, 4, 3000, "HLS 错误:xxx", 0, 1, 1),
    ]
    s = svc.summary(_DB(rows), days=7)
    assert s["sessions"] == 3
    assert s["ttff_ms_avg"] == 1600          # (800 + 2400) / 2
    assert s["ttff_ms_p95"] == 2400
    # 原因归并：细节 "HLS 错误:xxx" 归到 "HLS 错误"
    assert s["fallback_reasons"] == {"HLS 错误": 1}
    assert s["fallback_rate"] == round(1 / 3, 4)
    assert s["sw_cache_hit_rate"] == round(1 / 3, 4)
    assert s["level_distribution"] == {"自动": 2, "手动 L1": 1}


def test_record_event_throttle_rules():
    """节流：无降级原因的密集上报丢弃；带降级原因的必须放行。"""
    from src.services import video_qoe_service as svc

    added = []

    class _DB:
        def add(self, obj):
            added.append(obj)

        def commit(self):
            pass

    class _Video:
        id = 999  # 用独立 id，避免与其他用例共享节流状态

    base = dict(
        ttff_ms=100, waiting_count=0, waiting_ms=0, level=0, auto_level=0,
        manual=False, fallback_reason="", downgrades=0, sw_cached=False, elapsed_ms=0,
    )
    svc._last_report.pop(_Video.id, None)

    svc.record_event(_DB(), _Video(), **base)
    assert len(added) == 1, "首条应落库"

    svc.record_event(_DB(), _Video(), **base)
    assert len(added) == 1, "30s 内的无因重复上报应被丢弃"

    svc.record_event(_DB(), _Video(), **{**base, "fallback_reason": "mp4_fallback"})
    assert len(added) == 2, "带降级原因必须绕过节流"

    svc._last_report.pop(_Video.id, None)
