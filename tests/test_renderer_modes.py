from pathlib import Path

from smart_reels.models import MediaInfo, RenderSettings
from smart_reels.renderer import _ffmpeg_color, _video_chain
from smart_reels.tracking import CropPoint


MEDIA = MediaInfo(Path("source.mp4"), 10.0, 1920, 1080, 30.0, True)


def test_fit_color_keeps_whole_video_and_pads_background(tmp_path):
    settings = RenderSettings(tmp_path, video_mode="fit_color", background_color="#345678")
    chain = _video_chain(MEDIA, None, "subtitles=test.ass", settings)
    assert "force_original_aspect_ratio=decrease" in chain
    assert "pad=1080:1920" in chain
    assert "color=0x345678" in chain


def test_fit_blur_builds_background_and_foreground_layers(tmp_path):
    settings = RenderSettings(tmp_path, video_mode="fit_blur")
    chain = _video_chain(MEDIA, None, "subtitles=test.ass", settings)
    assert "split=2[bgsrc][fgsrc]" in chain
    assert "gblur=sigma=28" in chain
    assert "[bg][fg]overlay=" in chain


def test_invalid_ffmpeg_color_uses_safe_default():
    assert _ffmpeg_color("not-a-color") == "0x101814"


def test_smart_crop_normalizes_source_before_dynamic_filters(tmp_path):
    settings = RenderSettings(tmp_path, video_mode="smart_crop")
    chain = _video_chain(MEDIA, [CropPoint(0.0, 960.0, 540.0)], "subtitles=test.ass", settings)
    assert "scale=1920:1080:flags=bicubic,setsar=1,format=yuv420p,split=2" in chain
