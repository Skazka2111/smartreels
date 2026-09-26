import json

from smart_reels.api import OpenAICompatibleClient, _extract_json, _transcript_parts, deduplicate_clips
from smart_reels.models import ApiSettings, ClipCandidate, Transcript, Word


def test_extract_json_from_fence():
    assert _extract_json('```json\n{"clips": []}\n```') == {"clips": []}


def test_deduplicate_prefers_higher_score():
    clips = [
        ClipCandidate(10, 60, 70, "weak"),
        ClipCandidate(15, 62, 91, "strong"),
        ClipCandidate(100, 150, 80, "different"),
    ]
    result = deduplicate_clips(clips)
    assert [item.title for item in result] == ["strong", "different"]


def test_long_transcript_is_split_with_global_timestamps():
    words = [Word(float(second), float(second) + 0.2, str(second)) for second in range(0, 3700, 10)]
    parts = _transcript_parts(Transcript("", words))
    assert len(parts) == 3
    assert parts[1].words[0].start > 0


def test_transcription_adapter_reads_word_timestamps(tmp_path, monkeypatch):
    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"text": "Привет", "language": "ru", "words": [{"start": 1, "end": 1.5, "word": "Привет"}]}

    monkeypatch.setattr("smart_reels.api.httpx.post", lambda *args, **kwargs: Response())
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"test")
    client = OpenAICompatibleClient(ApiSettings(transcription_key="secret"))
    result = client.transcribe_file(audio, offset=10)
    assert result.words[0].start == 11


def test_analysis_adapter_parses_candidates(monkeypatch):
    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            content = json.dumps({"clips": [{"start": 10, "end": 50, "score": 91, "title": "Тест"}]})
            return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr("smart_reels.api.httpx.post", lambda *args, **kwargs: Response())
    settings = ApiSettings(analysis_key="secret")
    transcript = Transcript("слово " * 100, [Word(i, i + .2, "слово") for i in range(100)])
    clips = OpenAICompatibleClient(settings).find_clips(transcript, video_duration=100)
    assert len(clips) == 1
    assert clips[0].score == 91
