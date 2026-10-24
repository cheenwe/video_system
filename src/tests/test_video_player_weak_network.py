"""播放器弱网策略的配置锁定测试。

仓库没有 JS 测试运行器，因此这里读取 `web/js/video-player.js` 的源码，
断言弱网计划里要求的参数与行为锚点存在。目的是防止后续改动悄悄把
缓冲调大、退避去掉、降档逻辑删掉——这些正是弱网收益的来源。

真正的行为验收（限速 1–2 Mbps 观察 waiting 次数与是否落到 360p）
见 docs/weak-network-playback.md 的手工验收步骤。
"""
from __future__ import annotations

from pathlib import Path

PLAYER_JS = Path(__file__).resolve().parents[1].parent / "web" / "js" / "video-player.js"


def _source() -> str:
    return PLAYER_JS.read_text(encoding="utf-8")


def test_weak_network_constants_are_defined():
    src = _source()
    for anchor in (
        "maxBufferLength: 15",
        "maxMaxBufferLength: 60",
        "maxBufferHole: 0.3",
        "fragLoadingTimeOut: 10000",
        "manifestLoadingTimeOut: 10000",
        "fragLoadingMaxRetry: 4",
        "manifestLoadingMaxRetry: 3",
        # 有限指数退避（1s/2s/4s）后才允许回退 MP4
        "networkRetryDelays: [1000, 2000, 4000]",
        # 连续卡顿降档阈值与冷却
        "stallDowngradeMs: 6000",
        "stallWindowMs: 10000",
        "downgradeCooldownMs: 15000",
    ):
        assert anchor in src, f"缺少弱网参数: {anchor}"


def test_network_error_retries_before_mp4_fallback():
    """致命网络错误必须先退避重试，不能一次 error 就销毁 HLS。"""
    src = _source()
    assert "scheduleNetworkRetry" in src
    assert "hlsInstance.startLoad()" in src
    # 重试次数用尽才回退，且 UI 文案区分「重连中」与「已切 MP4」
    assert "netRetryCount >= WEAK.networkRetryDelays.length" in src
    assert "正在重连（第" in src
    assert "已切换 MP4 继续播放" in src


def test_auto_downgrade_on_stall():
    src = _source()
    assert "function maybeDowngrade" in src
    assert "hlsInstance.nextLevel = target" in src
    # 降档只在自动模式下进行；手动锁定不干预
    assert "if (!hlsInstance || manualLevel >= 0) return;" in src


def test_manual_quality_and_smooth_mode():
    """清晰度菜单 + 流畅优先：锁定最低档并关闭自动升档。"""
    src = _source()
    assert "video-player-quality-sel" in src
    assert "video-player-quality-smooth" in src
    assert "hlsInstance.autoLevelEnabled = false" in src
    assert "hlsInstance.currentLevel = idx" in src


def test_qoe_collection_is_exposed():
    src = _source()
    for anchor in (
        "ttffMs",
        "waitingCount",
        "waitingMs",
        "fallbackReason",
        "getQoe",
        "downgrades",
    ):
        assert anchor in src, f"缺少 QoE 字段: {anchor}"


def test_mp4_fallback_still_works():
    """既有回退路径必须保留（弱网优化的前提是不破坏可用性）。"""
    src = _source()
    assert "attachMp4" in src
    assert "播放模式：MP4 渐进加载" in src
    assert "startPlaybackSource" in src


def test_player_css_has_quality_controls():
    css = (PLAYER_JS.parent.parent / "css" / "video-hub.css").read_text(encoding="utf-8")
    for cls in (
        ".video-player-quality",
        ".video-player-quality-sel",
        ".video-player-quality-smooth",
        ".video-player-quality-smooth.active",
    ):
        assert cls in css, f"缺少样式: {cls}"
