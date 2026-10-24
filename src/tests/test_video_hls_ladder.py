"""HLS 多码率阶梯 / 关键帧对齐 / 真实码率探测的单元测试。

覆盖弱网优化计划 P0 的前三项验收：
- ABR ≥3 档（含 ≤360p）的生成逻辑
- 关键帧对齐参数写入 ffmpeg 命令
- master.m3u8 的 BANDWIDTH 来自探测而非常量
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core import video_streaming
from src.services import video_hls_service as hls
from src.services.video_transcode_service import MediaProbe


def _probe(height: int = 1080, fps: float = 25.0) -> MediaProbe:
    return MediaProbe(
        duration_sec=60,
        video_codec="h264",
        audio_codec="aac",
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
        width=height * 16 // 9,
        height=height,
        fps=fps,
    )


# ---------- 档位阶梯 ----------


def test_ladder_has_at_least_three_variants_for_hd_sources():
    """≥720p 源必须至少有 480p + 360p 两个低清档（加主档共 3 档）。"""
    for src_h in (1080, 720):
        rungs = hls.ladder_for_source(src_h)
        names = [r.name for r in rungs]
        assert "480p" in names, names
        assert "360p" in names, names


def test_ladder_includes_240p_only_when_enabled(monkeypatch):
    """240p 是成本开关，默认关闭；开启后 1080p 源才生成。"""
    assert "240p" not in [r.name for r in hls.ladder_for_source(1080)]
    monkeypatch.setattr(hls.settings, "VIDEO_HLS_240P", True)
    assert "240p" in [r.name for r in hls.ladder_for_source(1080)]
    # 720p 源默认不含 240p（阶梯上限由源高度决定）
    assert "240p" not in [r.name for r in hls.ladder_for_source(720)]


def test_ladder_skips_downscale_for_small_sources():
    """小分辨率源不再降档（升档只会浪费磁盘与 CPU）。"""
    assert hls.ladder_for_source(360) == []
    assert hls.ladder_for_source(0) == []
    # 480p 源只保留一档 360p
    assert [r.name for r in hls.ladder_for_source(480)] == ["360p"]


def test_segment_sec_differs_for_low_rungs():
    """弱网低档用更短切片；主档保持默认时长。"""
    low = hls.ladder_for_source(1080)[0]
    assert hls.segment_sec_for(low) == hls.settings.VIDEO_HLS_LOW_SEGMENT_SEC
    assert hls.segment_sec_for(None) == hls.settings.VIDEO_HLS_SEGMENT_SEC


# ---------- 关键帧对齐 ----------


def test_gop_args_align_to_segment_seconds():
    args = hls._gop_args(4, 25.0)
    # 4s * 25fps = 100 帧 GOP，且显式强制在切片边界打关键帧
    assert args[args.index("-g") + 1] == "100"
    assert args[args.index("-keyint_min") + 1] == "100"
    assert "expr:gte(t,n_forced*4)" in args
    # 关闭自适应插帧，否则画面切换会打出额外关键帧，切片长度不可控
    assert args[args.index("-sc_threshold") + 1] == "0"


def test_gop_args_fallback_when_fps_unknown():
    """探测不到帧率时用 25fps 兜底，而不是把 GOP 算成 0。"""
    args = hls._gop_args(6, 0.0)
    assert args[args.index("-g") + 1] == "150"


# ---------- master.m3u8 ----------


def test_master_playlist_contains_real_bandwidth_and_independent_segments(tmp_path: Path):
    master = tmp_path / "master.m3u8"
    hls._write_master(
        master,
        [
            (2_400_000, "stream_0/playlist.m3u8", 1920, 1080, 2_100_000),
            (900_000, "stream_1/playlist.m3u8", 854, 480, 800_000),
            (560_000, "stream_2/playlist.m3u8", 640, 360, 500_000),
        ],
    )
    text = master.read_text(encoding="utf-8")
    assert "#EXT-X-INDEPENDENT-SEGMENTS" in text
    # 码率必须逐档递减，hls.js 才能据此选档
    assert "BANDWIDTH=2400000" in text
    assert "BANDWIDTH=900000" in text
    assert "BANDWIDTH=560000" in text
    # 探测到的平均码率单独写出，帮助 ABR 估算
    assert "AVERAGE-BANDWIDTH=2100000" in text
    assert 'CODECS="avc1.4d401f,mp4a.40.2"' in text
    assert text.count("#EXT-X-STREAM-INF") == 3
    # 档位顺序：主档在前
    assert text.index("stream_0/playlist.m3u8") < text.index("stream_1/playlist.m3u8")


def test_master_playlist_omits_average_bandwidth_when_unknown(tmp_path: Path):
    master = tmp_path / "master.m3u8"
    hls._write_master(master, [(1_200_000, "stream_0/playlist.m3u8", 640, 360, 0)])
    text = master.read_text(encoding="utf-8")
    assert "AVERAGE-BANDWIDTH" not in text
    assert "BANDWIDTH=1200000" in text


def test_variant_entry_uses_probed_bitrate(monkeypatch, tmp_path: Path):
    """BANDWIDTH 取探测峰值而非均值，避免 hls.js 低估该档带宽。"""
    playlist = tmp_path / "stream_1" / "playlist.m3u8"
    playlist.parent.mkdir(parents=True)
    playlist.write_text("#EXTM3U\n", encoding="utf-8")
    monkeypatch.setattr(hls, "probe_bitrate", lambda _p, _n: (800_000, 1_000_000))

    bw, rel, w, h, avg = hls._variant_entry(
        playlist, fallback_bps=500_000, width=640, height=360
    )
    assert avg == 800_000
    assert bw == 1_050_000  # 峰值 + 5% 余量
    assert rel == "stream_1/playlist.m3u8"
    assert (w, h) == (640, 360)


def test_variant_entry_falls_back_when_probe_unavailable(monkeypatch, tmp_path: Path):
    """ffprobe 不可用时回退到配置估值，绝不影响出片。"""
    playlist = tmp_path / "stream_0" / "playlist.m3u8"
    playlist.parent.mkdir(parents=True)
    playlist.write_text("#EXTM3U\n", encoding="utf-8")
    monkeypatch.setattr(hls, "probe_bitrate", lambda _p, _n: (0, 0))

    bw, _rel, _w, _h, avg = hls._variant_entry(
        playlist, fallback_bps=1_200_000, width=1920, height=1080
    )
    assert avg == 0
    assert bw == 1_200_000


def _write_playlist(dir_path: Path, entries: list[tuple[str, float]]) -> Path:
    """写一个 VOD media playlist；entries: (分段文件名, 时长秒)。"""
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:6", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for name, dur in entries:
        lines.append(f"#EXTINF:{dur:.6f},")
        lines.append(name)
    pl = dir_path / "playlist.m3u8"
    pl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pl


def test_probe_bitrate_computes_from_segment_sizes(tmp_path: Path):
    """码率 = 分片字节 × 8 / 时长；不依赖 ffprobe 读 playlist。

    ffprobe 对 `.m3u8` 只统计 playlist 自身字节（实测 204 字节 → 54 bps），
    并不聚合分片，所以这里必须自己按分片体积计算。
    """
    entries = [("seg_000.ts", 4.0), ("seg_001.ts", 4.0)]
    pl = _write_playlist(tmp_path, entries)
    # 400_000 字节 / 4 秒 = 800_000 bps
    (tmp_path / "seg_000.ts").write_bytes(b"x" * 400_000)
    (tmp_path / "seg_001.ts").write_bytes(b"x" * 200_000)

    avg, peak = hls.probe_bitrate(pl, 5)
    # (400000+200000)*8/8s = 600_000 bps 平均
    assert avg == 600_000
    # 峰值取单片最大：400000*8/4 = 800_000
    assert peak == 800_000


def test_probe_bitrate_handles_missing_segments(tmp_path: Path):
    """分片缺失时只按实际读到的文件计算，不会抛错也不会虚高时长。"""
    entries = [("seg_000.ts", 4.0), ("seg_001.ts", 4.0), ("seg_002.ts", 4.0)]
    pl = _write_playlist(tmp_path, entries)
    (tmp_path / "seg_000.ts").write_bytes(b"x" * 100_000)
    (tmp_path / "seg_002.ts").write_bytes(b"x" * 300_000)
    avg, peak = hls.probe_bitrate(pl, 5)
    # 缺失的 seg_001 不计入分子也不计入分母：总时长 8s
    assert avg == (100_000 + 300_000) * 8 // 8
    assert peak == 300_000 * 8 // 4


def test_probe_bitrate_samples_evenly_for_long_videos(tmp_path: Path):
    """分段多于抽样上限时均匀抽样，避免只看片头（片头常偏低）。"""
    entries = [(f"seg_{i:03d}.ts", 4.0) for i in range(20)]
    pl = _write_playlist(tmp_path, entries)
    for i in range(20):
        # 第 10 片码率最高
        size = 500_000 if i == 10 else 100_000
        (tmp_path / f"seg_{i:03d}.ts").write_bytes(b"x" * size)
    _avg, peak = hls.probe_bitrate(pl, 5)
    assert peak == 100_000 * 8 // 4  # 抽样点未必命中最高分片
    # 抽样数为 0/空时退回全量
    _avg, peak_all = hls.probe_bitrate(pl, 0)
    assert peak_all == 500_000 * 8 // 4


def test_probe_bitrate_returns_zero_for_unparseable_playlist(tmp_path: Path):
    pl = tmp_path / "playlist.m3u8"
    pl.write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")
    assert hls.probe_bitrate(pl, 5) == (0, 0)

    missing = tmp_path / "nope.m3u8"
    assert hls.probe_bitrate(missing, 5) == (0, 0)


# ---------- 主档对齐决策 ----------


def test_keyframe_interval_parsing(monkeypatch):
    packets = [
        {"pts_time": "0.0", "flags": "K"},
        {"pts_time": "5.0", "flags": ""},
        {"pts_time": "10.0", "flags": "K"},
        {"pts_time": "15.0", "flags": ""},
        {"pts_time": "20.0", "flags": "K"},
    ]
    monkeypatch.setattr(hls, "_run_ffprobe", lambda _a: {"packets": packets})
    assert hls.probe_keyframe_interval(Path("/tmp/x.mp4")) == pytest.approx(10.0)


def test_keyframe_interval_zero_when_probe_fails(monkeypatch):
    monkeypatch.setattr(hls, "_run_ffprobe", lambda _a: None)
    assert hls.probe_keyframe_interval(Path("/tmp/x.mp4")) == 0.0
    monkeypatch.setattr(hls, "_run_ffprobe", lambda _a: {"packets": [{"pts_time": "0", "flags": "K"}]})
    assert hls.probe_keyframe_interval(Path("/tmp/x.mp4")) == 0.0


# ---------- MP4 Range 分块可配置 ----------


def test_stream_chunk_size_configurable(monkeypatch):
    monkeypatch.setattr(video_streaming.settings, "VIDEO_STREAM_CHUNK_KB", 64)
    assert video_streaming.default_chunk_size() == 64 * 1024
    # 非法/极端值被夹到安全范围，不会把服务打爆
    monkeypatch.setattr(video_streaming.settings, "VIDEO_STREAM_CHUNK_KB", 9999)
    assert video_streaming.default_chunk_size() == 4096 * 1024
    monkeypatch.setattr(video_streaming.settings, "VIDEO_STREAM_CHUNK_KB", 1)
    assert video_streaming.default_chunk_size() == 32 * 1024


def test_iter_file_range_respects_chunk_size(tmp_path: Path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"0123456789")
    # 闭区间 [2, 6]：共 5 字节，按 2 字节分块应输出 3 段
    out = b"".join(video_streaming.iter_file_range(f, 2, 6, chunk_size=2))
    assert out == b"23456"
    # 不传 chunk_size 时走配置默认值（256KB），这里数据小仍返回完整区间
    assert b"".join(video_streaming.iter_file_range(f, 0, 3)) == b"0123"
