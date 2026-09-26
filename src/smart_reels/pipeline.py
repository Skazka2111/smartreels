from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .api import OpenAICompatibleClient
from .media import MediaProbe
from .models import ApiSettings, ClipCandidate, MediaInfo, RenderSettings, Transcript, Word
from .renderer import ClipRenderer
from .transcription import transcribe_video


Progress = Callable[[int, str], None]


class SmartReelsPipeline:
    def __init__(
        self,
        project_dir: Path,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        fonts_dir: Path | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.cache_dir = project_dir / "cache"
        self.output_dir = project_dir / "results"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = ffmpeg
        self.probe = MediaProbe(ffprobe)
        self.renderer = ClipRenderer(ffmpeg, ffprobe, fonts_dir)

    def analyse(
        self,
        source: Path,
        api: ApiSettings,
        *,
        quality_mode: str = "balanced",
        progress: Progress | None = None,
        force: bool = False,
    ) -> tuple[MediaInfo, Transcript, list[ClipCandidate]]:
        notify = progress or (lambda percent, message: None)
        notify(2, "Проверка видео")
        media = self.probe.probe(source)
        if not media.has_audio:
            raise ValueError("В видео нет звуковой дорожки с речью.")
        key = self._cache_key(source)
        transcript_path = self.cache_dir / f"{key}_transcript.json"
        clips_path = self.cache_dir / f"{key}_{quality_mode}_clips.json"
        client = OpenAICompatibleClient(api)
        if transcript_path.exists() and not force:
            transcript = self._load_transcript(transcript_path)
            notify(40, "Использована сохранённая транскрибация")
        else:
            with tempfile.TemporaryDirectory(prefix="smart_reels_audio_") as work_name:
                transcript = transcribe_video(
                    source,
                    Path(work_name),
                    client,
                    ffmpeg=self.ffmpeg,
                    duration=media.duration,
                    progress=lambda message: notify(20, message),
                )
            self._save_transcript(transcript_path, transcript)
            notify(55, "Транскрибация готова")
        if clips_path.exists() and not force:
            clips = [ClipCandidate(**item) for item in json.loads(clips_path.read_text("utf-8"))]
            notify(95, "Использован сохранённый анализ")
        else:
            notify(65, "Поиск сильных фрагментов")
            clips = client.find_clips(transcript, video_duration=media.duration, quality_mode=quality_mode)
            clips_path.write_text(
                json.dumps([item.as_dict() for item in clips], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        notify(100, f"Найдено фрагментов: {len(clips)}")
        return media, transcript, clips

    def render_all(
        self,
        source: Path,
        media: MediaInfo,
        transcript: Transcript,
        clips: list[ClipCandidate],
        settings: RenderSettings,
        *,
        progress: Progress | None = None,
    ) -> list[Path]:
        notify = progress or (lambda percent, message: None)
        selected = [item for item in clips if item.selected]
        results: list[Path] = []
        for index, clip in enumerate(selected, start=1):
            base = int((index - 1) / max(1, len(selected)) * 100)
            notify(base, f"Ролик {index} из {len(selected)}: {clip.title}")
            result = self.renderer.render(
                source, media, transcript, clip, settings,
                index=index,
                progress=lambda message, base=base: notify(base, message),
            )
            results.append(result)
        notify(100, f"Готово роликов: {len(results)}")
        return results

    @staticmethod
    def _cache_key(path: Path) -> str:
        stat = path.stat()
        value = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()[:20]

    @staticmethod
    def _save_transcript(path: Path, transcript: Transcript) -> None:
        payload = {
            "text": transcript.text,
            "language": transcript.language,
            "words": [asdict(word) for word in transcript.words],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _load_transcript(path: Path) -> Transcript:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Transcript(
            text=payload["text"],
            language=payload.get("language"),
            words=[Word(**item) for item in payload.get("words", [])],
        )

