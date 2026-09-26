from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Callable

from .errors import RenderError
from .media import MediaProbe
from .models import ClipCandidate, MediaInfo, RenderSettings, Transcript
from .process import run_command
from .subtitles import create_ass
from .tracking import analyse_crop_path, crop_filter


class ClipRenderer:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", fonts_dir: Path | None = None) -> None:
        self.ffmpeg = ffmpeg
        self.probe = MediaProbe(ffprobe)
        self.fonts_dir = fonts_dir

    def render(
        self,
        source: Path,
        media: MediaInfo,
        transcript: Transcript,
        clip: ClipCandidate,
        settings: RenderSettings,
        *,
        index: int,
        progress: Callable[[str], None] | None = None,
    ) -> Path:
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{index:02d}_{clip.score}_{_safe_name(clip.title)}.mp4"
        final_path = _unique_path(settings.output_dir / filename)
        with tempfile.TemporaryDirectory(prefix="smart_reels_") as temp_name:
            temp = Path(temp_name)
            subtitles = create_ass(
                temp / "captions.ass", transcript, clip.start, clip.end,
                settings.subtitle, fonts_dir=self.fonts_dir,
            )
            path = None
            if settings.video_mode == "smart_crop":
                if progress:
                    progress(f"Отслеживание героя: {clip.title}")
                path = analyse_crop_path(source, media, clip.start, clip.end)
            elif progress:
                progress(f"Вписывание видео целиком: {clip.title}")
            main_path = temp / "main.mp4"
            self._render_main(source, media, clip, path, subtitles, settings, main_path, progress)
            if settings.outro_file and settings.outro_file.is_file():
                if progress:
                    progress(f"Добавление заставки: {clip.title}")
                self._append_outro(main_path, settings.outro_file, final_path, temp, progress)
            else:
                main_path.replace(final_path)
        self._verify(final_path, clip.duration)
        return final_path

    def _render_main(
        self,
        source: Path,
        media: MediaInfo,
        clip: ClipCandidate,
        crop_path,
        subtitles: Path,
        settings: RenderSettings,
        destination: Path,
        progress: Callable[[str], None] | None,
    ) -> None:
        duration = clip.duration
        subtitle_filter = f"subtitles=filename='{_filter_path(subtitles)}'"
        if self.fonts_dir and self.fonts_dir.is_dir():
            subtitle_filter += f":fontsdir='{_filter_path(self.fonts_dir)}'"
        command = [
            self.ffmpeg, "-y", "-ss", f"{clip.start:.3f}", "-t", f"{duration:.3f}",
            "-i", str(source),
        ]
        music_index = None
        if settings.music_file and settings.music_file.is_file():
            music_index = 1
            command.extend(["-stream_loop", "-1", "-i", str(settings.music_file)])

        video_chain = _video_chain(media, crop_path, subtitle_filter, settings)
        if music_index is not None:
            audio_chain = (
                f"[0:a]asetpts=PTS-STARTPTS,volume=1.0[voice];"
                f"[{music_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={settings.music_volume:.3f},afade=t=in:st=0:d=0.4,"
                f"afade=t=out:st={max(0.0, duration - 0.8):.3f}:d=0.8[music];"
                "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
            )
        else:
            audio_chain = "[0:a]asetpts=PTS-STARTPTS[a]"
        command.extend([
            "-filter_complex", f"{video_chain};{audio_chain}",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium",
            "-crf", "18" if settings.quality == "high" else "21",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest", str(destination),
        ])
        run_command(command, progress=progress)

    def _append_outro(
        self,
        main: Path,
        outro: Path,
        destination: Path,
        temp: Path,
        progress: Callable[[str], None] | None,
    ) -> None:
        outro_info = self.probe.probe(outro)
        normalized = temp / "outro.mp4"
        command = [self.ffmpeg, "-y", "-i", str(outro)]
        if not outro_info.has_audio:
            command.extend(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
        video_filter = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30,format=yuv420p"
        )
        command.extend([
            "-vf", video_filter,
            "-map", "0:v:0", "-map", "0:a:0" if outro_info.has_audio else "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-shortest", str(normalized),
        ])
        run_command(command, progress=progress)
        listing = temp / "concat.txt"
        listing.write_text(
            f"file '{_concat_path(main)}'\nfile '{_concat_path(normalized)}'\n",
            encoding="utf-8",
        )
        try:
            run_command([
                self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                "-c", "copy", "-movflags", "+faststart", str(destination),
            ], progress=progress)
        except Exception:
            run_command([
                self.ffmpeg, "-y", "-i", str(main), "-i", str(normalized),
                "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "21",
                "-c:a", "aac", "-b:a", "192k", str(destination),
            ], progress=progress)

    def _verify(self, path: Path, expected_minimum: float) -> None:
        try:
            info = self.probe.probe(path)
        except Exception as exc:
            raise RenderError(f"Готовый ролик не прошёл проверку: {exc}") from exc
        if not info.has_audio or info.duration < expected_minimum - 1.0:
            raise RenderError("Готовый ролик получился короче ожидаемого или без звука.")


def _safe_name(value: str) -> str:
    name = re.sub(r"[^\w\-а-яА-ЯёЁ ]+", "", value, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)
    return name[:60] or "clip"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 1000):
        candidate = path.with_stem(f"{path.stem}_{number}")
        if not candidate.exists():
            return candidate
    raise RenderError("Не удалось подобрать свободное имя для результата.")


def _filter_path(path: Path) -> str:
    text = str(path.resolve()).replace("\\", "/")
    return text.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")


def _concat_path(path: Path) -> str:
    return str(path.resolve()).replace("'", r"'\''").replace("\\", "/")


def _video_chain(
    media: MediaInfo,
    crop_path,
    subtitle_filter: str,
    settings: RenderSettings,
) -> str:
    if settings.video_mode == "fit_color":
        return (
            "[0:v]setpts=PTS-STARTPTS,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={_ffmpeg_color(settings.background_color)},"
            f"{subtitle_filter},fps=30,format=yuv420p[v]"
        )
    if settings.video_mode == "fit_blur":
        return (
            "[0:v]setpts=PTS-STARTPTS,split=2[bgsrc][fgsrc];"
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=28[bg];"
            "[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{subtitle_filter},"
            "fps=30,format=yuv420p[v]"
        )
    video_filter = crop_filter(media, crop_path)
    return (
        f"[0:v]setpts=PTS-STARTPTS,scale={media.width}:{media.height}:flags=bicubic,"
        "setsar=1,format=yuv420p,split=2[smartbgsrc][smartfgsrc];"
        "[smartbgsrc]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=28[smartbg];"
        f"[smartfgsrc]{video_filter}[smartfg];"
        f"[smartbg][smartfg]overlay=0:0,{subtitle_filter},fps=30,format=yuv420p[v]"
    )


def _ffmpeg_color(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return "0x" + value[1:]
    return "0x101814"
