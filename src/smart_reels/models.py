from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Word:
    start: float
    end: float
    text: str

    @classmethod
    def from_dict(cls, value: dict[str, Any], offset: float = 0.0) -> "Word":
        return cls(
            start=max(0.0, float(value.get("start", 0))) + offset,
            end=max(0.0, float(value.get("end", value.get("start", 0)))) + offset,
            text=str(value.get("word", value.get("text", ""))).strip(),
        )


@dataclass(slots=True)
class Transcript:
    text: str
    words: list[Word] = field(default_factory=list)
    language: str | None = None

    def as_timestamped_text(self, interval: float = 10.0) -> str:
        if not self.words:
            return self.text
        lines: list[str] = []
        bucket: list[str] = []
        bucket_start = self.words[0].start
        for word in self.words:
            if bucket and word.start - bucket_start >= interval:
                lines.append(f"[{format_time(bucket_start)}] {' '.join(bucket)}")
                bucket = []
                bucket_start = word.start
            bucket.append(word.text)
        if bucket:
            lines.append(f"[{format_time(bucket_start)}] {' '.join(bucket)}")
        return "\n".join(lines)


@dataclass(slots=True)
class ClipCandidate:
    start: float
    end: float
    score: int
    title: str
    reason: str = ""
    hook: str = ""
    selected: bool = True

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


@dataclass(slots=True)
class SubtitleStyle:
    mode: str = "highlight"
    font_name: str = "Montserrat Bold"
    font_size: int = 68
    primary_color: str = "#FFFFFF"
    active_color: str = "#39FF88"
    outline_color: str = "#101010"
    background_color: str = "#000000"
    background_opacity: int = 115
    outline: int = 5
    position: str = "bottom"
    margin_v: int = 420
    max_words: int = 6
    font_file: str = ""
    effect: str = "background"
    background_padding: int = 36
    background_corner_radius: int = 24
    glow_color: str = "#39FF88"
    glow_opacity: int = 200
    glow_radius: int = 18


@dataclass(slots=True)
class ApiSettings:
    transcription_base_url: str = "https://api.openai.com/v1"
    transcription_model: str = "whisper-1"
    transcription_key: str = ""
    analysis_base_url: str = "https://api.openai.com/v1"
    analysis_model: str = "gpt-4.1-mini"
    analysis_key: str = ""


@dataclass(slots=True)
class RenderSettings:
    output_dir: Path
    subtitle: SubtitleStyle = field(default_factory=SubtitleStyle)
    music_file: Path | None = None
    music_volume: float = 0.10
    outro_file: Path | None = None
    video_mode: str = "smart_crop"
    background_color: str = "#101814"
    quality: str = "standard"


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def parse_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return 0.0
    if ":" not in text:
        return float(text)
    parts = [float(part) for part in text.split(":")]
    total = 0.0
    for part in parts:
        total = total * 60 + part
    return total
