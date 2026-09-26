from __future__ import annotations

from pathlib import Path
from typing import Callable

from .api import OpenAICompatibleClient
from .models import Transcript
from .process import run_command


def transcribe_video(
    source: Path,
    work_dir: Path,
    client: OpenAICompatibleClient,
    *,
    ffmpeg: str = "ffmpeg",
    duration: float,
    progress: Callable[[str], None] | None = None,
) -> Transcript:
    """Extract small MP3 chunks and merge API word timestamps."""
    chunk_length = 1200.0
    chunks: list[Path] = []
    cursor = 0.0
    while cursor < duration:
        chunk = work_dir / f"audio_{len(chunks):03d}.mp3"
        part_duration = min(chunk_length, duration - cursor)
        run_command(
            [
                ffmpeg, "-y", "-ss", f"{cursor:.3f}", "-t", f"{part_duration:.3f}",
                "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                "-b:a", "40k", str(chunk),
            ],
            progress=progress,
        )
        chunks.append(chunk)
        cursor += part_duration

    merged_words = []
    texts: list[str] = []
    cursor = 0.0
    language = None
    for index, chunk in enumerate(chunks, start=1):
        if progress:
            progress(f"Транскрибация: часть {index} из {len(chunks)}")
        transcript = client.transcribe_file(chunk, offset=cursor)
        texts.append(transcript.text)
        merged_words.extend(transcript.words)
        language = language or transcript.language
        cursor += min(chunk_length, max(0.0, duration - cursor))
    return Transcript(text=" ".join(texts).strip(), words=merged_words, language=language)

