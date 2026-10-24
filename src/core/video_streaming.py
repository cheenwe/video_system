"""MP4 渐进式播放：解析 Range 请求并分块输出，便于弱网边下边播。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from src.core.config import settings

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_DEFAULT_CHUNK = 256 * 1024  # 256KB，弱网下减少单次等待


def default_chunk_size() -> int:
    """单次分块大小（字节），由 VIDEO_STREAM_CHUNK_KB 控制。

    弱网调小（如 64KB）可降低单次等待与失败重传成本；调大则提高吞吐。
    """
    kb = getattr(settings, "VIDEO_STREAM_CHUNK_KB", 256) or 256
    return max(32, min(int(kb), 4096)) * 1024


def parse_range_header(range_header: str, file_size: int) -> Optional[tuple[int, int]]:
    """解析 Range 头，返回 (start, end) 闭区间；非法则 None。"""
    m = _RANGE_RE.match((range_header or "").strip())
    if not m:
        return None
    start_s, end_s = m.groups()
    if not start_s and not end_s:
        return None
    if not start_s:
        suffix = int(end_s)
        if suffix <= 0:
            return None
        start = max(0, file_size - suffix)
        end = file_size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    if start < 0 or end < start or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end


def iter_file_range(
    path: Path,
    start: int,
    end: int,
    chunk_size: int | None = None,
) -> Iterator[bytes]:
    """按分块输出 [start, end] 区间；chunk_size 为空时用配置值。"""
    size = chunk_size or default_chunk_size()
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = fh.read(min(size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _base_headers(media_type: str, file_size: int) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
        "Content-Disposition": "inline",
        "Cache-Control": "private, max-age=3600",
        "Content-Length": str(file_size),
    }


def rewrite_hls_playlist(content: str, video_id: int, query: str, base_dir: str = "") -> str:
    """将 m3u8 内相对 URI 改写为带鉴权参数的 API 地址。

    base_dir 是当前 playlist 在 HLS 目录内的相对目录（如 "stream_1"）。
    VOD 的 master.m3u8 指向 `stream_1/playlist.m3u8`，而该 playlist 内的
    分段写的是裸 `seg_000.ts`——若不带 base_dir，改写结果会丢掉 stream_1/
    前缀而指向不存在的路径。master 自身（base_dir 为空）不受影响。
    """
    q = query.strip("&")
    suffix = ("?" + q) if q else ""
    base = (base_dir or "").strip("/")
    prefix = f"/api/videos/{video_id}/hls/"
    if base:
        prefix += base + "/"
    out: list[str] = []
    for line in content.splitlines():
        raw = line.strip()
        if not raw:
            out.append(line)
            continue
        if raw.startswith("#"):
            # fMP4 的初始化段写在 #EXT-X-MAP:URI="init.mp4" 里；不改写的话
            # 浏览器会按相对路径请求 /hls/stream_N/init.mp4——不带鉴权参数，
            # 需要登录的视频会 403。
            out.append(_rewrite_map_uri(raw, prefix, suffix))
            continue
        if raw.startswith("http://") or raw.startswith("https://"):
            out.append(line)
            continue
        uri = raw.split("?", 1)[0]
        # 分段已是绝对路径（历史数据或外部改写）时保持原样，避免拼出双前缀
        if uri.startswith("/api/videos/"):
            out.append(line)
            continue
        out.append(prefix + uri + suffix)
    return "\n".join(out) + "\n"


def _rewrite_map_uri(line: str, prefix: str, suffix: str) -> str:
    """改写 #EXT-X-MAP:URI="..." 中的相对 URI；其余注释行原样返回。"""
    key = "#EXT-X-MAP:URI="
    idx = line.find(key)
    if idx < 0:
        return line
    rest = line[idx + len(key) :]
    quote = rest[:1]
    if quote not in {'"', "'"}:
        return line
    end = rest.find(quote, 1)
    if end < 0:
        return line
    uri = rest[1:end]
    if not uri or uri.startswith("http://") or uri.startswith("https://") or uri.startswith("/api/videos/"):
        return line
    return line[: idx + len(key)] + quote + prefix + uri + suffix + quote + rest[end + 1 :]


def build_video_stream_response(request: Request, path: Path, media_type: str) -> Response:
    """按 Range 返回 206 分块或 200 全量流，支持 HEAD。"""
    st = path.stat()
    file_size = st.st_size
    if file_size <= 0:
        return Response(status_code=404)

    range_header = request.headers.get("range")
    if range_header:
        parsed = parse_range_header(range_header, file_size)
        if parsed is None:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        start, end = parsed
        length = end - start + 1
        headers = _base_headers(media_type, length)
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        if request.method == "HEAD":
            return Response(status_code=206, headers=headers)
        return StreamingResponse(
            iter_file_range(path, start, end),
            status_code=206,
            headers=headers,
            media_type=media_type,
        )

    headers = _base_headers(media_type, file_size)
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers)
    return StreamingResponse(
        iter_file_range(path, 0, file_size - 1),
        status_code=200,
        headers=headers,
        media_type=media_type,
    )
