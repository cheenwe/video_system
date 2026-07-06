"""上传后转码为浏览器可播的 MP4（H.264 + AAC）。"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.core.config import settings
from src.core.exceptions import BizError

logger = logging.getLogger(__name__)

# 容器/扩展名在多数浏览器中无法直接播放
_FORCE_TRANSCODE_EXTENSIONS = frozenset(
    {
        ".mov",
        ".mkv",
        ".avi",
        ".wmv",
        ".flv",
        ".mpeg",
        ".mpg",
        ".3gp",
        ".ts",
        ".m2ts",
        ".webm",
    }
)

_WEB_VIDEO_CODEC = "h264"
_WEB_AUDIO_CODECS = frozenset({"aac", "mp3"})

_EXT_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".m4v": "video/mp4",
}


def _mime_for_path(path: Path) -> str:
    return _EXT_MIME.get(path.suffix.lower(), "video/mp4")


@dataclass(frozen=True)
class MediaProbe:
    duration_sec: int
    video_codec: str | None
    audio_codec: str | None
    format_name: str | None


@dataclass(frozen=True)
class PreparedVideo:
    path: Path
    mime_type: str
    file_size: int
    duration_sec: int


def _bin_available(name: str) -> bool:
    return shutil.which(name) is not None


def ffmpeg_available() -> bool:
    return _bin_available(settings.FFMPEG_BIN)


def ffprobe_available() -> bool:
    return _bin_available(settings.FFPROBE_BIN)


def needs_transcode_by_extension(path: Path) -> bool:
    return path.suffix.lower() in _FORCE_TRANSCODE_EXTENSIONS


def _normalize_codec(name: str | None) -> str | None:
    if not name:
        return None
    n = name.lower().strip()
    if n in {"h264", "avc", "avc1"}:
        return "h264"
    if n in {"hevc", "h265"}:
        return "hevc"
    if n in {"aac", "mp4a"}:
        return "aac"
    return n


def probe_media(path: Path) -> MediaProbe:
    if not path.is_file():
        raise BizError("视频文件不存在")
    if not ffprobe_available():
        return MediaProbe(duration_sec=0, video_codec=None, audio_codec=None, format_name=None)

    proc = subprocess.run(
        [
            settings.FFPROBE_BIN,
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name",
            "-show_entries",
            "stream=codec_name,codec_type",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        logger.warning("ffprobe failed for %s: %s", path.name, (proc.stderr or "")[-500:])
        return MediaProbe(duration_sec=0, video_codec=None, audio_codec=None, format_name=None)

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return MediaProbe(duration_sec=0, video_codec=None, audio_codec=None, format_name=None)

    duration = 0
    try:
        duration = int(float(data.get("format", {}).get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0

    video_codec = None
    audio_codec = None
    for stream in data.get("streams") or []:
        ctype = stream.get("codec_type")
        codec = _normalize_codec(stream.get("codec_name"))
        if ctype == "video" and video_codec is None:
            video_codec = codec
        elif ctype == "audio" and audio_codec is None:
            audio_codec = codec

    fmt = data.get("format", {}).get("format_name")
    return MediaProbe(duration, video_codec, audio_codec, fmt)


def _codecs_web_playable(probe: MediaProbe) -> bool:
    if probe.video_codec != _WEB_VIDEO_CODEC:
        return False
    if probe.audio_codec and probe.audio_codec not in _WEB_AUDIO_CODECS:
        return False
    return True


def needs_transcode(path: Path, probe: MediaProbe | None = None) -> bool:
    if not settings.VIDEO_TRANSCODE_ENABLED:
        return False
    if needs_transcode_by_extension(path):
        return True
    p = probe if probe is not None else probe_media(path)
    if path.suffix.lower() in {".mp4", ".m4v"}:
        return not _codecs_web_playable(p)
    if p.video_codec is None:
        return True
    return not _codecs_web_playable(p)


def transcode_to_mp4(src: Path, dest: Path, probe: MediaProbe | None = None) -> None:
    if not ffmpeg_available():
        raise BizError(
            "当前环境未安装 ffmpeg，无法转码 MOV/MKV 等格式，请上传 MP4(H.264+AAC) 或联系管理员",
            500,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    p = probe or probe_media(src)
    can_copy = _codecs_web_playable(p)

    cmd = [
        settings.FFMPEG_BIN,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
    ]
    if can_copy:
        cmd.extend(["-c", "copy"])
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
        if p.audio_codec:
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.append("-an")
    cmd.extend(["-movflags", "+faststart", str(dest)])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.VIDEO_TRANSCODE_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        dest.unlink(missing_ok=True)
        raise BizError(f"视频转码超时（>{settings.VIDEO_TRANSCODE_TIMEOUT_SEC}s）", 500) from exc

    if proc.returncode != 0:
        dest.unlink(missing_ok=True)
        err = (proc.stderr or proc.stdout or "转码失败").strip()
        raise BizError(f"视频转码失败: {err[-300:]}", 500)
    if not dest.is_file() or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise BizError("视频转码未生成有效文件", 500)


def _write_web_mp4(src: Path, dest: Path, probe: MediaProbe) -> None:
    """写入标准 MP4；源与目标同路径时用临时文件，避免 ffmpeg 原地覆盖失败。"""
    if src.resolve() == dest.resolve():
        tmp = dest.parent / f"{dest.stem}.faststart.tmp.mp4"
        try:
            transcode_to_mp4(src, tmp, probe)
            tmp.replace(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    else:
        transcode_to_mp4(src, dest, probe)


def prepare_for_web_playback(src: Path, upload_id: str) -> PreparedVideo:
    """必要时转码/重封装为 MP4，并返回最终路径与元数据。"""
    if not src.is_file():
        raise BizError("视频文件不存在，请重新上传")

    probe = probe_media(src)
    target = src.parent / f"{upload_id}.mp4"

    if not settings.VIDEO_TRANSCODE_ENABLED:
        out = src
    elif needs_transcode(src, probe):
        _write_web_mp4(src, target, probe)
        if src.resolve() != target.resolve():
            src.unlink(missing_ok=True)
        out = target
    else:
        # H.264+AAC 等可拷贝：仍重封装并写入 faststart，避免 moov 在文件尾导致无法从头播放
        _write_web_mp4(src, target, probe)
        if src.resolve() != target.resolve():
            src.unlink(missing_ok=True)
        out = target

    final_probe = probe_media(out)
    duration = final_probe.duration_sec or probe.duration_sec
    return PreparedVideo(
        path=out,
        mime_type=_mime_for_path(out),
        file_size=out.stat().st_size,
        duration_sec=max(0, duration),
    )
