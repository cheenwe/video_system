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
