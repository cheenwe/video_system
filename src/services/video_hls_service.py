"""HLS 切片：上传后生成多码率 m3u8，弱网自适应播放。

设计要点（弱网优先「能播完」而非「高清」）：
- **档位阶梯**：按源高度决定档位集合，保证弱网至少能落到 360p（可选 240p），
  不浪费小分辨率视频的转码。
- **关键帧对齐**：转码档强制 GOP 与切片时长对齐；主档若源关键帧间隔过大，
  改为对齐重编码而不是 `-c:v copy`（copy 插不进关键帧）。
- **真实码率**：生成后用 ffprobe 探测各档平均/峰值码率写入
  `EXT-X-STREAM-INF`，不用硬编码估值，hls.js 的 ABR 才不会高估带宽。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.core.config import settings
from src.core.exceptions import BizError
from src.models.video import Video
from src.services.video_transcode_service import MediaProbe, ffmpeg_available

logger = logging.getLogger(__name__)

_M3U8_CT = "application/vnd.apple.mpegurl"
_TS_CT = "video/mp2t"


@dataclass(frozen=True)
class Variant:
    """一个 HLS 档位。

    - height: 目标高度；0 表示主档（保持源分辨率）
    - target_video_kbps: 视频目标码率（用于 -maxrate/-bufsize 与兜底 BANDWIDTH）
    - low: 弱网档，用更短切片加快起播与切档
    """

    name: str
    height: int
    target_video_kbps: int
    audio_kbps: int = 96
    copy: bool = False
    low: bool = False


# 档位按「从高到低」排列；主档（源分辨率）单独生成，不在此表。
# 码率取值参考 H.264 16:9 的经验值：高度越高、码率越高。
_RUNGS: tuple[Variant, ...] = (
    Variant(name="480p", height=480, target_video_kbps=800, low=True),
    Variant(name="360p", height=360, target_video_kbps=500, low=True),
    Variant(name="240p", height=240, target_video_kbps=300, low=True),
)

# 各源高度对应的低清档位阶梯（不含主档）
_LADDER_BY_SOURCE_HEIGHT: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1080, ("480p", "360p", "240p")),
    (720, ("480p", "360p")),
    (480, ("360p",)),
    (0, ()),
)


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


def ladder_for_source(src_height: int) -> list[Variant]:
    """按源高度返回要生成的低清档位；源太小则不再降档（避免无效转码）。"""
    h = src_height or 0
    names: tuple[str, ...] = ()
    for min_h, allowed in _LADDER_BY_SOURCE_HEIGHT:
        if h >= min_h:
            names = allowed
            break
    if not settings.VIDEO_HLS_240P:
        names = tuple(n for n in names if n != "240p")
    return [v for v in _RUNGS if v.name in names]


def segment_sec_for(variant: Variant | None) -> int:
    """弱网低档用更短切片，加快起播与切档；高清档保持默认时长。"""
    if variant is not None and variant.low:
        return settings.VIDEO_HLS_LOW_SEGMENT_SEC
    return settings.VIDEO_HLS_SEGMENT_SEC


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


def _run_ffprobe(args: list[str]) -> dict | None:
    from src.services.video_transcode_service import ffprobe_available

    if not ffprobe_available():
        return None
    try:
        proc = subprocess.run(
            [settings.FFPROBE_BIN, "-v", "error", *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None


def probe_keyframe_interval(src: Path) -> float:
    """源视频关键帧平均间隔（秒）；探测失败返回 0（表示未知）。"""
    data = _run_ffprobe(
        [
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=pts_time,flags",
            "-of",
            "json",
            str(src),
        ]
    )
    if not data:
        return 0.0
    times: list[float] = []
    for pkt in data.get("packets") or []:
        flags = str(pkt.get("flags") or "")
        if "K" not in flags:
            continue
        try:
            times.append(float(pkt.get("pts_time") or 0))
        except (TypeError, ValueError):
            continue
    if len(times) < 2:
        return 0.0
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not gaps:
        return 0.0
    return sum(gaps) / len(gaps)


def _parse_media_playlist(playlist: Path) -> tuple[list[str], list[float]]:
    """解析 media playlist，返回 (分段文件名, 每段时长秒)。

    只处理 ffmpeg 生成的 VOD playlist：`#EXTINF:<dur>,` 后跟一行分段 URI。
    无法解析时返回空列表，由调用方走兜底。
    """
    try:
        lines = playlist.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], []
    names: list[str] = []
    durs: list[float] = []
    pending_dur: float | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            try:
                pending_dur = float(line.split(":", 1)[1].split(",", 1)[0])
            except (IndexError, ValueError):
                pending_dur = None
            continue
        if line.startswith("#"):
            continue
        if pending_dur is None:
            continue
        uri = line.split("?", 1)[0]
        names.append(os.path.basename(uri))
        durs.append(pending_dur)
        pending_dur = None
    return names, durs


def probe_bitrate(playlist: Path, max_samples: int) -> tuple[int, int]:
    """探测某档的真实 (平均码率, 峰值码率) bps。

    平均码率 = 全部分片字节数 × 8 / 总时长；峰值码率 = 单片码率的最大值
    （分段极多时按 max_samples 抽样，避免长视频上做无用功）。

    不用 ffprobe 读 playlist：它对 `.m3u8` 只统计 playlist 自身字节
    （实测 204 字节 → 54 bps），并不聚合分片，得出的码率完全不可用。
    """
    names, durs = _parse_media_playlist(playlist)
    if not names or not durs:
        return 0, 0

    total_bytes = 0
    total_dur = 0.0
    rates: list[int] = []
    for name, dur in zip(names, durs):
        try:
            size = (playlist.parent / name).stat().st_size
        except OSError:
            continue
        if dur <= 0:
            continue
        total_bytes += size
        total_dur += dur
        rates.append(int(size * 8 / dur))
    if total_dur <= 0 or total_bytes <= 0:
        return 0, 0

    avg = int(total_bytes * 8 / total_dur)
    if max_samples and len(rates) > max_samples:
        # 均匀抽样，避免只看开头几个分片（片头常偏低）
        step = len(rates) / float(max_samples)
        picked = [rates[int(i * step)] for i in range(max_samples)]
        peak = max(picked)
    else:
        peak = max(rates)
    return avg, peak


def _audio_bitrate() -> str:
    """所有档位共用的音频码率。

    切档时音频参数不一致会产生可闻的爆音；统一后只剩视频分辨率变化。
    """
    return f"{settings.VIDEO_HLS_UNIFIED_AUDIO_KBPS}k"


def _segment_ext() -> str:
    return "m4s" if settings.VIDEO_HLS_SEGMENT_FORMAT == "fmp4" else "ts"


def _hls_output_args(stream_dir: Path, playlist: Path, segment_sec: int) -> list[str]:
    """HLS 输出参数；按配置选择 mpegts 或 fMP4(CMAF) 封装。

    fMP4 用 `init.mp4` + `seg_NNN.m4s`，播放器可按字节范围取片段，
    切档与 seek 都更快；代价是老浏览器（不支持 CMFA 的 hls.js 版本）不可用，
    因此默认仍是 mpegts，由部署方按客户端情况切换。
    """
    ext = _segment_ext()
    args = [
        "-hls_time",
        str(segment_sec),
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(stream_dir / f"seg_%03d.{ext}"),
        "-f",
        "hls",
        str(playlist),
    ]
    if ext == "m4s":
        args = [
            "-hls_segment_type",
            "fmp4",
            "-hls_fmp4_init_filename",
            "init.mp4",
            *args,
        ]
    return args


def _gop_args(segment_sec: int, fps: float) -> list[str]:
    """关键帧与切片时长对齐的参数。

    `force_key_frames` 用「分段整数倍」保证每个切片起点都是关键帧；`-g` /
    `-keyint_min` 兜底（部分源不遵守场景表达式），`-sc_threshold 0` 关掉自适应
    插帧，否则画面切换会额外插关键帧，导致切片长度与预期不符。
    """
    fps = fps if fps and fps > 0 else 25.0
    gop = max(1, int(round(segment_sec * fps)))
    return [
        "-g",
        str(gop),
        "-keyint_min",
        str(gop),
        "-sc_threshold",
        "0",
        "-force_key_frames",
        f"expr:gte(t,n_forced*{segment_sec})",
    ]


def _hls_copy_stream(
    src: Path,
    stream_dir: Path,
    probe: MediaProbe,
    segment_sec: int,
    *,
    align: bool,
) -> tuple[int, int]:
    """主档：源关键帧已对齐时直接拷贝；否则按 GOP 对齐重编码。"""
    stream_dir.mkdir(parents=True, exist_ok=True)
    playlist = stream_dir / "playlist.m3u8"
    has_audio = bool(probe.audio_codec)
    can_copy_video = probe.video_codec == "h264"

    cmd = [settings.FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if can_copy_video and not align:
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
                *_gop_args(segment_sec, probe.fps),
            ]
        )
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", _audio_bitrate()])
    else:
        cmd.append("-an")
    cmd.extend(_hls_output_args(stream_dir, playlist, segment_sec))
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
    fps: float,
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
        # force_divisible_by=2 必须显式写：16:9 源降到 480p 时
        # `scale=-2:480` 会算出 853x480（奇数宽），libx264 直接报
        # "width not divisible by 2" 而整个档位失败。
        "-vf",
        f"scale=-2:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2",
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
        *_gop_args(segment_sec, fps),
    ]
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", _audio_bitrate()])
    else:
        cmd.append("-an")
    cmd.extend(_hls_output_args(stream_dir, playlist, segment_sec))
    _run_ffmpeg(cmd, f"{height}p")
    w = max(2, int(height * 16 / 9)) if height else 0
    return w, height


def _write_master(path: Path, variants: list[tuple[int, str, int, int, int]]) -> None:
    """variants: (bandwidth, playlist_rel, width, height, average_bandwidth)"""
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for bw, pl, w, h, avg in variants:
        attrs = [f"BANDWIDTH={bw}"]
        if avg > 0:
            # 与 BANDWIDTH 不同的平均码率帮助 hls.js 更准确估算带宽
            attrs.append(f"AVERAGE-BANDWIDTH={avg}")
        if w > 0 and h > 0:
            attrs.append(f"RESOLUTION={w}x{h}")
        attrs.append('CODECS="avc1.4d401f,mp4a.40.2"')
        lines.append("#EXT-X-STREAM-INF:" + ",".join(attrs))
        lines.append(pl)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _variant_entry(
    playlist: Path, *, fallback_bps: int, width: int, height: int
) -> tuple[int, str, int, int, int]:
    """探测真实码率；失败时回退到配置估值（BANDWIDTH 至少为 1）。"""
    rel = f"{playlist.parent.name}/playlist.m3u8"
    bw, avg = fallback_bps, 0
    if settings.VIDEO_HLS_PROBE_BITRATE:
        probed_avg, probed_peak = probe_bitrate(playlist, settings.VIDEO_HLS_PROBE_SAMPLE_SEGMENTS)
        if probed_avg > 0:
            avg = probed_avg
            # BANDWIDTH 应偏峰值而非均值，否则 hls.js 会持续低估该档带宽
            bw = max(probed_peak or probed_avg, 1)
            bw = int(bw * 1.05)  # 5% 余量，避免选档后立即触发切换
    return bw, rel, width, height, avg


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

    has_audio = bool(p.audio_codec)
    src_h = p.height or 0

    # 主档是否需要对齐重编码：copy 无法插入关键帧，源 GOP 明显大于切片时长时，
    # 弱网下切档/seek 会命中非关键帧，卡顿窗口被拉长。
    align_main = False
    if settings.VIDEO_HLS_KEYFRAME_ALIGN and p.video_codec == "h264":
        kf = probe_keyframe_interval(src)
        if kf > 0 and kf > settings.VIDEO_HLS_SEGMENT_SEC * 1.5:
            align_main = True
            logger.info(
                "HLS 主档改为对齐重编码 upload_id=%s keyframe_interval=%.2fs", upload_id, kf
            )

    w0, h0 = _hls_copy_stream(src, out_root / "stream_0", p, segment_sec_for(None), align=align_main)
    variants: list[tuple[int, str, int, int, int]] = [
        _variant_entry(
            out_root / "stream_0" / "playlist.m3u8",
            fallback_bps=2_500_000 if (h0 or src_h) >= 720 else 1_200_000,
            width=w0,
            height=h0,
        )
    ]

    ladder = (
        ladder_for_source(src_h)
        if (settings.VIDEO_HLS_ABR and settings.VIDEO_HLS_ABR_LADDER)
        else []
    )
    for idx, rung in enumerate(ladder, start=1):
        w, h = _hls_transcode_stream(
            src,
            out_root / f"stream_{idx}",
            height=rung.height,
            bandwidth=rung.target_video_kbps * 1000,
            segment_sec=segment_sec_for(rung),
            has_audio=has_audio,
            fps=p.fps,
        )
        variants.append(
            _variant_entry(
                out_root / f"stream_{idx}" / "playlist.m3u8",
                fallback_bps=(rung.target_video_kbps + rung.audio_kbps) * 1000,
                width=w,
                height=h,
            )
        )

    master = master_playlist_path(upload_id)
    _write_master(master, variants)
    logger.info(
        "HLS 已生成 upload_id=%s variants=%s ladder=%s",
        upload_id,
        len(variants),
        [r.name for r in ladder] or "仅主档",
    )

    # 配置了对象存储时后台同步；失败不影响本地播放（下次生成会重试）
    if settings.VIDEO_HLS_SYNC_STORAGE:
        try:
            from src.services import video_storage

            video_storage.sync_hls_async(upload_id, out_root)
        except Exception as exc:  # 同步线程启动失败不应让出片失败
            logger.warning("HLS 对象存储同步未启动 upload_id=%s: %s", upload_id, exc)
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
    # fMP4(CMAF)：init.mp4 是初始化段，.m4s 是媒体段
    if ext == ".mp4":
        return "video/mp4"
    if ext == ".m4s":
        return "video/iso.segment"
    return "application/octet-stream"
