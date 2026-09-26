from pathlib import Path

from smart_reels.models import MediaInfo
from smart_reels.tracking import (
    CropPoint,
    _deduplicate_faces,
    _limit_expression_points,
    _load_yunet_detector,
    _reduce_points,
    crop_filter,
)


def test_horizontal_video_gets_dynamic_horizontal_crop():
    media = MediaInfo(Path("video.mp4"), 10, 1920, 1080, 30, True)
    result = crop_filter(media, [CropPoint(0, 400, 500), CropPoint(1, 1200, 500)])
    assert "crop=608:1080" in result
    assert "pad=iw+608:ih:304:0" in result
    assert "format=rgba" in result
    assert "color=black@0" in result
    assert "clip((t-0.000)/1.000,0,1)" in result
    assert "if(isnan(t)," in result
    assert "scale=1080:1920" in result


def test_vertical_video_never_crops_outside_height():
    media = MediaInfo(Path("video.mp4"), 10, 720, 1600, 30, True)
    result = crop_filter(media, [CropPoint(0, 360, 800)])
    assert "crop=720:1280" in result


def test_overlapping_face_detections_are_merged():
    faces = _deduplicate_faces([(100, 100, 120, 120), (110, 105, 115, 115), (500, 90, 90, 90)])
    assert len(faces) == 2


def test_edge_face_is_centred_with_mirror_padding():
    media = MediaInfo(Path("video.mp4"), 10, 1920, 1080, 30, True)
    result = crop_filter(media, [CropPoint(0, 1900, 500)])
    assert "x='1900.00'" in result


def test_yunet_model_is_bundled_and_loadable():
    assert _load_yunet_detector() is not None


def test_reduced_path_keeps_changes_across_the_whole_clip():
    points = [CropPoint(index * 0.35, index * 100.0, 500.0) for index in range(8)]
    reduced = _reduce_points(points, minimum_gap=0.7)
    assert len(reduced) >= 4
    assert reduced[0].time == 0.0
    assert reduced[-1].time == points[-1].time
    assert reduced[0].center_x != reduced[-1].center_x


def test_long_path_uses_flat_expression_instead_of_nested_if():
    media = MediaInfo(Path("video.mp4"), 95, 1920, 1080, 30, True)
    points = [CropPoint(index * 0.72, 300.0 + (index % 9) * 100.0, 500.0) for index in range(132)]
    result = crop_filter(media, points)
    assert "clip(" in result
    assert "if(lt(" not in result
    assert "if(isnan(t)," in result
    assert result.count("clip(") <= 47


def test_expression_limit_preserves_large_speaker_switches():
    points = [CropPoint(index * 0.72, 300.0, 500.0) for index in range(132)]
    values = [300.0 for _ in points]
    values[67] = 1500.0
    reduced_points, reduced_values = _limit_expression_points(points, values)
    assert len(reduced_points) == 48
    assert reduced_values[0] == 300.0
    assert reduced_values[-1] == 300.0
    assert 1500.0 in reduced_values
