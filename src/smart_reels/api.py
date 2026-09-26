from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import httpx

from .errors import ApiError
from .models import ApiSettings, ClipCandidate, Transcript, Word, parse_time


def _endpoint(base_url: str, suffix: str) -> str:
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("error", payload)
        if isinstance(detail, dict):
            detail = detail.get("message", detail)
        return str(detail)
    except Exception:
        return response.text[:1000]


class OpenAICompatibleClient:
    """Adapters for OpenAI-compatible transcription and chat endpoints."""

    def __init__(self, settings: ApiSettings, timeout: float = 180.0) -> None:
        self.settings = settings
        self.timeout = timeout

    def transcribe_file(self, audio: Path, *, offset: float = 0.0) -> Transcript:
        if not self.settings.transcription_key.strip():
            raise ApiError("Укажите API-ключ сервиса транскрибации.")
        url = _endpoint(self.settings.transcription_base_url, "audio/transcriptions")
        headers = {"Authorization": f"Bearer {self.settings.transcription_key.strip()}"}
        data = {
            "model": self.settings.transcription_model.strip(),
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        try:
            with audio.open("rb") as stream:
                response = httpx.post(
                    url,
                    headers=headers,
                    data=data,
                    files={"file": (audio.name, stream, "audio/mpeg")},
                    timeout=self.timeout,
                )
        except httpx.HTTPError as exc:
            raise ApiError(f"Не удалось обратиться к транскрибации: {exc}") from exc
        if response.status_code >= 400:
            raise ApiError(
                f"Транскрибация вернула {response.status_code}: {_error_message(response)}"
            )
        payload = response.json()
        words = [
            Word.from_dict(item, offset)
            for item in payload.get("words", [])
            if str(item.get("word", item.get("text", ""))).strip()
        ]
        if not words:
            for segment in payload.get("segments", []):
                words.append(
                    Word(
                        float(segment.get("start", 0)) + offset,
                        float(segment.get("end", segment.get("start", 0))) + offset,
                        str(segment.get("text", "")).strip(),
                    )
                )
        text = str(payload.get("text", "")).strip()
        if not text and words:
            text = " ".join(item.text for item in words)
        if not text:
            raise ApiError("Сервис не распознал речь в аудио.")
        return Transcript(text=text, words=words, language=payload.get("language"))

    def find_clips(
        self,
        transcript: Transcript,
        *,
        video_duration: float,
        quality_mode: str = "balanced",
    ) -> list[ClipCandidate]:
        if not self.settings.analysis_key.strip():
            raise ApiError("Укажите API-ключ нейросети для анализа текста.")
        parts = _transcript_parts(transcript)
        clips: list[ClipCandidate] = []
        for part in parts:
            clips.extend(self._find_clips_part(part, video_duration, quality_mode))
        snapped = [_snap_to_speech(item, transcript.words, video_duration) for item in clips]
        return deduplicate_clips(snapped)

    def _find_clips_part(
        self,
        transcript: Transcript,
        video_duration: float,
        quality_mode: str,
    ) -> list[ClipCandidate]:
        timestamped = transcript.as_timestamped_text(interval=8.0)
        prompt = _analysis_prompt(timestamped, video_duration, quality_mode)
        url = _endpoint(self.settings.analysis_base_url, "chat/completions")
        headers = {
            "Authorization": f"Bearer {self.settings.analysis_key.strip()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.analysis_model.strip(),
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "Ты редактор коротких вертикальных видео. Возвращай только JSON."},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ApiError(f"Не удалось выполнить анализ: {exc}") from exc
        if response.status_code >= 400:
            raise ApiError(f"Анализ вернул {response.status_code}: {_error_message(response)}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = _extract_json(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ApiError("Нейросеть вернула ответ, который не удалось прочитать как JSON.") from exc
        raw_clips = result if isinstance(result, list) else result.get("clips", [])
        clips: list[ClipCandidate] = []
        for item in raw_clips:
            try:
                start = max(0.0, parse_time(item.get("start", 0)))
                end = min(video_duration, parse_time(item.get("end", 0)))
                if end - start < 20 or end - start > 110:
                    continue
                clips.append(
                    ClipCandidate(
                        start=start,
                        end=end,
                        score=max(0, min(100, int(item.get("score", 0)))),
                        title=str(item.get("title", "Фрагмент")).strip()[:100],
                        reason=str(item.get("reason", "")).strip()[:500],
                        hook=str(item.get("hook", "")).strip()[:300],
                    )
                )
            except (ValueError, TypeError):
                continue
        return clips


def _analysis_prompt(transcript: str, duration: float, quality_mode: str) -> str:
    threshold = {"strict": 82, "balanced": 70, "maximum": 58}.get(quality_mode, 70)
    return f"""
Проанализируй расшифровку видео длительностью {duration:.2f} секунд и найди ВСЕ
самостоятельные фрагменты с вирусным потенциалом и оценкой не ниже {threshold}/100.

Правила:
- целевая длина 30–90 секунд; допустимо 20–110 секунд только ради законченной мысли;
- фрагмент обязан начинаться понятно без предыдущего контекста;
- не начинай с середины предложения и не заканчивай до завершения мысли;
- не выбирай почти одинаковые или сильно пересекающиеся фрагменты;
- оценивай конкретику, конфликт, пользу, эмоцию, неожиданность и сильную формулировку;
- не придумывай то, чего нет в тексте;
- время укажи в секундах относительно начала видео.

Верни строго JSON:
{{"clips":[{{"start":12.3,"end":67.8,"score":88,"title":"Короткий заголовок",
"hook":"Первая цепляющая мысль","reason":"Почему фрагмент самостоятельный и сильный"}}]}}

Расшифровка:
{transcript}
""".strip()


def _extract_json(content: str) -> dict | list:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


def deduplicate_clips(clips: list[ClipCandidate]) -> list[ClipCandidate]:
    chosen: list[ClipCandidate] = []
    for clip in sorted(clips, key=lambda item: (-item.score, item.start)):
        duplicate = False
        for existing in chosen:
            overlap = max(0.0, min(clip.end, existing.end) - max(clip.start, existing.start))
            shorter = max(0.001, min(clip.duration, existing.duration))
            if overlap / shorter >= 0.55:
                duplicate = True
                break
        if not duplicate:
            chosen.append(clip)
    return sorted(chosen, key=lambda item: (-item.score, item.start))


def _transcript_parts(transcript: Transcript, window: float = 1800.0, overlap: float = 60.0) -> list[Transcript]:
    if not transcript.words or transcript.words[-1].end <= window:
        return [transcript]
    result: list[Transcript] = []
    cursor = 0.0
    end = transcript.words[-1].end
    while cursor < end:
        limit = cursor + window
        words = [word for word in transcript.words if word.end > cursor and word.start < limit]
        if words:
            result.append(Transcript(" ".join(word.text for word in words), words, transcript.language))
        cursor += window - overlap
    return result


def _snap_to_speech(clip: ClipCandidate, words: list[Word], duration: float) -> ClipCandidate:
    if not words:
        return clip
    start_index = min(range(len(words)), key=lambda index: abs(words[index].start - clip.start))
    end_index = min(range(len(words)), key=lambda index: abs(words[index].end - clip.end))
    lower_bound = max(0.0, clip.start - 10.0)
    while start_index > 0:
        previous = words[start_index - 1]
        current = words[start_index]
        if previous.end < lower_bound or current.start - previous.end > 0.8 or previous.text.rstrip().endswith((".", "!", "?")):
            break
        start_index -= 1
    upper_bound = min(duration, clip.end + 12.0)
    while end_index + 1 < len(words):
        current = words[end_index]
        following = words[end_index + 1]
        if current.end > upper_bound or current.text.rstrip().endswith((".", "!", "?")) or following.start - current.end > 0.8:
            break
        end_index += 1
    start = max(0.0, words[start_index].start - 0.12)
    end = min(duration, words[end_index].end + 0.18)
    if 20.0 <= end - start <= 110.0:
        clip.start = start
        clip.end = end
    return clip
