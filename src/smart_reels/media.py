from __future__ import annotations

import json
from pathlib import Path

from .errors import MediaError
from .models import MediaInfo
from .process import run_command


class MediaProbe:
    def __init__(self, ffprobe: str = "ffprobe") -> None:
        self.ffprobe = ffprobe

    def probe(self, path: str | Path) -> MediaInfo:
        source = Path(path)
        result = run_command(
            [
                self.ffprobe,
                "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate",
                "-of", "json",
                str(source),
            ]
        )
        try:
            payload = json.loads(result.stdout)
            video = next(item for item in payload["streams"] if item.get("codec_type") == "video")
            rate_text = video.get("avg_frame_rate", "30/1")
            numerator, denominator = rate_text.split("/", 1)
            fps = float(numerator) / max(1.0, float(denominator))
            return MediaInfo(
                path=source,
                duration=float(payload["format"]["duration"]),
                width=int(video["width"]),
                height=int(video["height"]),
                fps=fps or 30.0,
                has_audio=any(item.get("codec_type") == "audio" for item in payload["streams"]),
            )
        except (KeyError, StopIteration, ValueError, TypeError) as exc:
            raise MediaError(f"Не удалось прочитать параметры видео «{source.name}».") from exc

