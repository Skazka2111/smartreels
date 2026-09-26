from pathlib import Path

import pytest

from smart_reels.models import SubtitleStyle, Transcript, Word
from smart_reels.subtitles import create_ass


def test_create_highlight_ass(tmp_path):
    transcript = Transcript("Привет мир", [Word(10.0, 10.4, "Привет"), Word(10.5, 10.9, "мир")])
    target = create_ass(tmp_path / "captions.ass", transcript, 10.0, 12.0, SubtitleStyle())
    text = target.read_text(encoding="utf-8-sig")
    assert "\\kf40" in text
    assert "Привет" in text
    assert "Dialogue:" in text


def test_segment_timestamps_fall_back_to_phrase(tmp_path):
    transcript = Transcript("Одна длинная фраза", [Word(0.0, 2.0, "Одна длинная фраза")])
    target = create_ass(tmp_path / "captions.ass", transcript, 0.0, 3.0, SubtitleStyle(mode="highlight"))
    text = target.read_text(encoding="utf-8-sig")
    assert "\\kf" not in text


def test_top_subtitles_use_top_alignment(tmp_path):
    transcript = Transcript("Тест", [Word(0.0, 0.5, "Тест")])
    style = SubtitleStyle(position="top", margin_v=360)
    text = create_ass(tmp_path / "top.ass", transcript, 0.0, 1.0, style).read_text(encoding="utf-8-sig")
    assert ",8,70,70,360,1" in text


def test_word_popup_has_overshoot_and_spring_back(tmp_path):
    transcript = Transcript("Привет", [Word(0.0, 0.5, "Привет")])
    style = SubtitleStyle(mode="word_pop")
    text = create_ass(tmp_path / "popup.ass", transcript, 0.0, 1.0, style).read_text(encoding="utf-8-sig")
    assert r"\fscx120\fscy120" in text
    assert r"\fscx94\fscy94" in text


def test_rounded_background_is_wider_than_text_and_keeps_top_position(tmp_path):
    transcript = Transcript("Привет", [Word(0.0, 1.0, "Привет")])
    style = SubtitleStyle(position="top", background_padding=60, background_corner_radius=30)
    content = create_ass(tmp_path / "round.ass", transcript, 0, 1, style).read_text(encoding="utf-8-sig")
    assert "\\p1" in content
    assert " b " in content
    assert "Dialogue: 0," in content and "Dialogue: 1," in content
    assert "\\an5\\pos(540," in content


@pytest.mark.parametrize("effect, expected", [("outline", ",1,5,0,"), ("glow", "\\blur9")])
def test_outline_or_glow_replaces_background(tmp_path, effect, expected):
    transcript = Transcript("Привет", [Word(0.0, 1.0, "Привет")])
    content = create_ass(tmp_path / "effect.ass", transcript, 0, 1,
                         SubtitleStyle(effect=effect)).read_text(encoding="utf-8-sig")
    assert expected in content
    assert "\\p1" not in content


def test_custom_font_uses_its_embedded_family_and_rejects_missing_file(tmp_path):
    font = Path(__file__).resolve().parents[1] / "portable_template" / "fonts" / "Montserrat-Bold.ttf"
    style = SubtitleStyle(font_file=font.name)
    transcript = Transcript("Текст", [Word(0, 1, "Текст")])
    with pytest.raises(ValueError, match="не найден"):
        create_ass(tmp_path / "missing.ass", transcript, 0, 1, style, fonts_dir=tmp_path)
    content = create_ass(tmp_path / "custom.ass", transcript, 0, 1, style,
                         fonts_dir=font.parent).read_text(encoding="utf-8-sig")
    assert "Style: Default,Montserrat," in content


@pytest.mark.parametrize("effect", ["lines", "torn_paper", "paper_letters"])
def test_paper_styles_draw_shapes_behind_text(tmp_path, effect):
    transcript = Transcript("Два слова", [Word(0, 1, "Два"), Word(1, 2, "слова")])
    content = create_ass(tmp_path / "paper.ass", transcript, 0, 2,
                         SubtitleStyle(mode="phrase", effect=effect)).read_text(encoding="utf-8-sig")
    assert "\\p1" in content
    assert "Dialogue: 0," in content and "Dialogue: 1," in content
    if effect == "paper_letters":
        assert content.count("Dialogue: 0,") >= len("Дваслова")
