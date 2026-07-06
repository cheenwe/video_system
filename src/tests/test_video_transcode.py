from pathlib import Path

from src.services import video_transcode_service
from src.services.video_transcode_service import MediaProbe


def test_needs_transcode_by_extension_mov():
    assert video_transcode_service.needs_transcode_by_extension(Path("clip.MOV")) is True


def test_needs_transcode_by_extension_mp4():
    assert video_transcode_service.needs_transcode_by_extension(Path("clip.mp4")) is False


def test_needs_transcode_mp4_h264_aac_ok():
    probe = MediaProbe(duration_sec=10, video_codec="h264", audio_codec="aac", format_name="mov,mp4")
    assert video_transcode_service.needs_transcode(Path("a.mp4"), probe) is False


def test_needs_transcode_mp4_hevc():
    probe = MediaProbe(duration_sec=10, video_codec="hevc", audio_codec="aac", format_name="mp4")
    assert video_transcode_service.needs_transcode(Path("a.mp4"), probe) is True


def test_needs_transcode_mov_even_if_h264():
    probe = MediaProbe(duration_sec=10, video_codec="h264", audio_codec="aac", format_name="mov")
    assert video_transcode_service.needs_transcode(Path("a.mov"), probe) is True
