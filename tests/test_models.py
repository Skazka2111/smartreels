from smart_reels.models import Transcript, Word, format_time, parse_time


def test_time_helpers():
    assert parse_time("01:02:03.5") == 3723.5
    assert parse_time("02:03") == 123.0
    assert format_time(3723.5) == "01:02:03.50"


def test_timestamped_transcript_keeps_global_time():
    transcript = Transcript("", [Word(65.0, 65.4, "Привет"), Word(66.0, 66.3, "мир")])
    assert transcript.as_timestamped_text().startswith("[00:01:05.00]")

