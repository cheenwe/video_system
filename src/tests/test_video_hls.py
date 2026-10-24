from src.core.video_streaming import rewrite_hls_playlist


def test_rewrite_playlist_relative_uri():
    content = "#EXTM3U\n#EXT-X-VERSION:3\nstream_0/playlist.m3u8\n"
    out = rewrite_hls_playlist(content, 42, "token=abc&v=xyz")
    assert "/api/videos/42/hls/stream_0/playlist.m3u8?token=abc&v=xyz" in out


def test_rewrite_playlist_segment_lines():
    content = "#EXTINF:6.0,\nseg_001.ts\n"
    out = rewrite_hls_playlist(content, 1, "token=t")
    assert out.strip().endswith("/api/videos/1/hls/seg_001.ts?token=t")


def test_rewrite_playlist_keeps_comments():
    content = "#EXT-X-TARGETDURATION:6\nseg.ts\n"
    out = rewrite_hls_playlist(content, 2, "")
    assert "#EXT-X-TARGETDURATION:6" in out
    assert "/api/videos/2/hls/seg.ts" in out


def test_rewrite_playlist_keeps_variant_directory():
    """变体 playlist 的分段必须带上自己的目录。

    master.m3u8 指向 stream_1/playlist.m3u8，而该 playlist 里写的是裸
    seg_000.ts；不带 base_dir 改写会得到 /hls/seg_000.ts（404）。
    """
    content = "#EXTM3U\n#EXTINF:4.0,\nseg_000.ts\n#EXTINF:4.0,\nseg_001.ts\n"
    out = rewrite_hls_playlist(content, 7, "token=t", "stream_1")
    assert "/api/videos/7/hls/stream_1/seg_000.ts?token=t" in out
    assert "/api/videos/7/hls/stream_1/seg_001.ts?token=t" in out
    # 不能出现丢掉目录的旧路径
    assert "/api/videos/7/hls/seg_000.ts" not in out


def test_rewrite_playlist_master_has_no_base_dir():
    """master 自身在根目录，base_dir 为空时行为与旧版一致。"""
    out = rewrite_hls_playlist("stream_0/playlist.m3u8\n", 3, "token=t", "")
    assert "/api/videos/3/hls/stream_0/playlist.m3u8?token=t" in out


def test_rewrite_playlist_does_not_double_prefix():
    """已是 API 绝对路径的 URI 保持原样，避免拼出双前缀。"""
    content = "/api/videos/9/hls/stream_0/seg_000.ts\n"
    out = rewrite_hls_playlist(content, 9, "token=t", "stream_0")
    assert out.count("/api/videos/9/hls/") == 1
