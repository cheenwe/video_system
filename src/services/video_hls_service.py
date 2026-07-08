"""HLS 切片：上传后生成多码率 m3u8，弱网自适应播放。"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.core.config import settings
from src.core.exceptions import BizError
from src.models.video import Video
from src.services.video_transcode_service import MediaProbe, ffmpeg_available

logger = logging.getLogger(__name__)

_M3U8_CT = "application/vnd.apple.mpegurl"
_TS_CT = "video/mp2t"


def storage_key_from_path(file_path: str) -> str:
    return Path(file_path).stem


def storage_key(video: Video) -> str:
    return storage_key_from_path(video.file_path)


def hls_dir(upload_id: str) -> Path:
    return settings.video_hls_root_path / upload_id


def master_playlist_path(upload_id: str) -> Path:
    return hls_dir(upload_id) / "master.m3u8"


def has_hls(video: Video) -> bool:
    return master_playlist_path(storage_key(video)).is_file()


def delete_hls(upload_id: str) -> None:
    root = hls_dir(upload_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def _run_ffmpeg(cmd: list[str], label: str) -> None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.VIDEO_HLS_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BizError(f"HLS {label} 超时（>{settings.VIDEO_HLS_TIMEOUT_SEC}s）", 500) from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffmpeg 失败").strip()
        raise BizError(f"HLS {label} 失败: {err[-400:]}", 500)


def _write_master(path: Path, variants: list[tuple[int, str, int, int]]) -> None:
    """variants: (bandwidth, playlist_rel, width, height)"""
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for bw, pl, w, h in variants:
        if w > 0 and h > 0:
            lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={w}x{h}")
        else:
            lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={bw}")
        lines.append(pl)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hls_copy_stream(src: Path, stream_dir: Path, probe: MediaProbe, segment_sec: int) -> tuple[int, int]:
    stream_dir.mkdir(parents=True, exist_ok=True)
    playlist = stream_dir / "playlist.m3u8"
    has_audio = bool(probe.audio_codec)
    can_copy_video = probe.video_codec == "h264"

    cmd = [settings.FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if can_copy_video:
        cmd.extend(["-c:v", "copy", "-bsf:v", "h264_mp4toannexb"])
    else:
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                settings.VIDEO_TRANSCODE_PRESET,
                "-crf",
                str(settings.VIDEO_TRANSCODE_CRF),
            ]
        )
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        cmd.append("-an")
    cmd.extend(
        [
            "-hls_time",
            str(segment_sec),
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(stream_dir / "seg_%03d.ts"),
            "-f",
            "hls",
            str(playlist),
        ]
    )
    _run_ffmpeg(cmd, "主档位")
    if not playlist.is_file():
        raise BizError("HLS 主档位未生成 playlist")
    return probe.width, probe.height


def _hls_transcode_stream(
    src: Path,
    stream_dir: Path,
    *,
    height: int,
    bandwidth: int,
    segment_sec: int,
    has_audio: bool,
) -> tuple[int, int]:
    stream_dir.mkdir(parents=True, exist_ok=True)
    playlist = stream_dir / "playlist.m3u8"
    cmd = [
        settings.FFMPEG_BIN,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vf",
        f"scale=-2:{height}:force_original_aspect_ratio=decrease",
        "-c:v",
        "libx264",
        "-preset",
        settings.VIDEO_TRANSCODE_PRESET,
        "-crf",
        str(min(settings.VIDEO_TRANSCODE_CRF + 2, 28)),
        "-maxrate",
        f"{max(bandwidth // 1000, 400)}k",
        "-bufsize",
        f"{max(bandwidth // 500, 800)}k",
    ]
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "96k"])
    else:
        cmd.append("-an")
    cmd.extend(
        [
            "-hls_time",
            str(segment_sec),
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(stream_dir / "seg_%03d.ts"),
            "-f",
            "hls",
            str(playlist),
        ]
    )
    _run_ffmpeg(cmd, f"{height}p")
    w = max(2, int(height * 16 / 9)) if height else 0
    return w, height


def generate_hls(src: Path, upload_id: str, probe: MediaProbe | None = None) -> Path:
    """从最终 MP4 生成 HLS；返回 master.m3u8 路径。"""
    if not settings.VIDEO_HLS_ENABLED:
        raise BizError("HLS 未启用")
    if not ffmpeg_available():
        raise BizError("未安装 ffmpeg，无法生成 HLS")
    if not src.is_file():
        raise BizError("源视频不存在")

    from src.services.video_transcode_service import probe_media

    p = probe or probe_media(src)
    out_root = hls_dir(upload_id)
    if out_root.exists():
        shutil.rmtree(out_root, ignore_errors=True)
    out_root.mkdir(parents=True, exist_ok=True)

    segment_sec = settings.VIDEO_HLS_SEGMENT_SEC
    has_audio = bool(p.audio_codec)
    src_h = p.height or 0

    w0, h0 = _hls_copy_stream(src, out_root / "stream_0", p, segment_sec)
    bw0 = 2_500_000 if (h0 or src_h) >= 720 else 1_200_000
    variants: list[tuple[int, str, int, int]] = [(bw0, "stream_0/playlist.m3u8", w0, h0)]

    if settings.VIDEO_HLS_ABR and (h0 or src_h) >= 720:
        w1, h1 = _hls_transcode_stream(
            src,
            out_root / "stream_1",
            height=480,
            bandwidth=800_000,
            segment_sec=segment_sec,
            has_audio=has_audio,
        )
        variants.append((800_000, "stream_1/playlist.m3u8", w1, h1))

    master = master_playlist_path(upload_id)
    _write_master(master, variants)
    logger.info("HLS 已生成 upload_id=%s variants=%s", upload_id, len(variants))
    return master


def resolve_hls_asset(upload_id: str, asset_path: str) -> Path:
    asset_path = (asset_path or "").strip().lstrip("/")
    if not asset_path or ".." in asset_path.split("/"):
        raise BizError("HLS 路径非法", 400)
    base = hls_dir(upload_id).resolve()
    full = (hls_dir(upload_id) / asset_path).resolve()
    if not str(full).startswith(str(base)):
        raise BizError("HLS 路径非法", 400)
    if not full.is_file():
        raise BizError("HLS 资源不存在", 404)
    return full


def media_type_for_asset(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".m3u8":
        return _M3U8_CT
    if ext == ".ts":
        return _TS_CT
    return "application/octet-stream"
