"""HLS 健康巡检判定。

判定的语义必须严格对账 master.m3u8 的声明：曾经只要求「master 在 + 任一
stream_* 目录有分片」，于是丢了两档的片子照样算健康，而 master 仍指向那两档，
自动档切过去直接 404/黑屏。这里把几种残缺形态都钉住。
"""
from pathlib import Path

import pytest

from src.services import video_hls_service, video_hls_housekeeping


class _Video:
    def __init__(self, key="sample"):
        self.id = 1
        self.file_path = f"/uploads/videos/{key}.mp4"


def _build(root: Path, variants: dict[str, dict]) -> None:
    """variants: {目录名: {"segs": [文件名], "init": bool}}"""
    lines = ["#EXTM3U", "#EXT-X-VERSION:6"]
    for name, cfg in variants.items():
        d = root / name
        d.mkdir(parents=True, exist_ok=True)
        body = ["#EXTM3U", "#EXT-X-TARGETDURATION:6"]
        if cfg.get("init"):
            (d / "init.mp4").write_bytes(b"\x00")
            body.append('#EXT-X-MAP:URI="init.mp4"')
        for i, seg in enumerate(cfg.get("segs", [])):
            (d / seg).write_bytes(b"\x00" * 16)
            body.append(f"#EXTINF:6.0,\n{seg}" if i == 0 else f"#EXTINF:6.0,\n{seg}")
        (d / "playlist.m3u8").write_text("\n".join(body) + "\n")
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360")
        lines.append(f"{name}/playlist.m3u8")
    (root / "master.m3u8").write_text("\n".join(lines) + "\n")


@pytest.fixture
def hls_root(tmp_path, monkeypatch):
    root = tmp_path / "hls"
    root.mkdir()
    monkeypatch.setattr(video_hls_service, "hls_dir", lambda _upload_id: root)
    return root


def test_healthy_when_all_variants_usable(hls_root):
    _build(hls_root, {"stream_0": {"segs": ["seg_000.ts", "seg_001.ts"]}})
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is True


def test_unhealthy_without_master(hls_root):
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is False


def test_unhealthy_when_declared_variant_dir_missing(hls_root):
    """master 声明了 stream_1，目录却被删掉：不能因为 stream_0 健在就算健康。"""
    _build(hls_root, {"stream_0": {"segs": ["seg_000.ts"]}})
    (hls_root / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nstream_0/playlist.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=300000\nstream_1/playlist.m3u8\n"
    )
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is False


def test_unhealthy_when_variant_has_no_segment(hls_root):
    d = hls_root / "stream_0"
    d.mkdir()
    (d / "playlist.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n")
    (hls_root / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nstream_0/playlist.m3u8\n"
    )
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is False


def test_fmp4_requires_init_segment(hls_root):
    """fMP4 少了 init.mp4，分片下载得到也解不出画面。"""
    d = hls_root / "stream_0"
    d.mkdir()
    for seg in ("seg_001.m4s", "seg_002.m4s"):
        (d / seg).write_bytes(b"\x00")
    (d / "playlist.m3u8").write_text(
        "#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\n#EXTINF:6.0,\nseg_001.m4s\n"
        "#EXTINF:6.0,\nseg_002.m4s\n#EXT-X-ENDLIST\n"
    )
    (hls_root / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nstream_0/playlist.m3u8\n"
    )
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is False

    (d / "init.mp4").write_bytes(b"\x00")
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is True


def test_unhealthy_when_trailing_segment_missing(hls_root):
    """首尾分片抽查：尾部缺失说明切片中断（磁盘满/进程被杀）。"""
    d = hls_root / "stream_0"
    d.mkdir()
    (d / "seg_000.ts").write_bytes(b"\x00")
    (d / "playlist.m3u8").write_text(
        "#EXTM3U\n#EXTINF:6.0,\nseg_000.ts\n#EXTINF:6.0,\nseg_001.ts\n#EXT-X-ENDLIST\n"
    )
    (hls_root / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nstream_0/playlist.m3u8\n"
    )
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is False


def test_master_without_variant_declaration_is_unhealthy(hls_root):
    (hls_root / "master.m3u8").write_text("#EXTM3U\n#EXT-X-VERSION:6\n")
    assert video_hls_housekeeping.HlsHousekeeper._is_healthy(_Video()) is False
