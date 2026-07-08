"""MP4 渐进式播放：解析 Range 请求并分块输出，便于弱网边下边播。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_DEFAULT_CHUNK = 256 * 1024  # 256KB，弱网下减少单次等待


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


def iter_file_range(path: Path, start: int, end: int, chunk_size: int = _DEFAULT_CHUNK) -> Iterator[bytes]:
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = fh.read(min(chunk_size, remaining))
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


def rewrite_hls_playlist(content: str, video_id: int, query: str) -> str:
    """将 m3u8 内相对 URI 改写为带鉴权参数的 API 地址。"""
    q = query.strip("&")
    suffix = ("?" + q) if q else ""
    out: list[str] = []
    for line in content.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            out.append(line)
            continue
        if raw.startswith("http://") or raw.startswith("https://"):
            out.append(line)
            continue
        uri = raw.split("?", 1)[0]
        out.append(f"/api/videos/{video_id}/hls/{uri}{suffix}")
    return "\n".join(out) + "\n"


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
