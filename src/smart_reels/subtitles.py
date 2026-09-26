from __future__ import annotations

from pathlib import Path
from PIL import ImageFont

from .models import SubtitleStyle, Transcript, Word


def create_ass(
    destination: Path,
    transcript: Transcript,
    clip_start: float,
    clip_end: float,
    style: SubtitleStyle,
    *,
    fonts_dir: Path | None = None,
) -> Path:
    words = [
        Word(max(0.0, word.start - clip_start), min(clip_end, word.end) - clip_start, word.text)
        for word in transcript.words
        if word.end > clip_start and word.start < clip_end and word.text.strip()
    ]
    font, font_name = _load_font(style, fonts_dir)
    header = _header(style, font_name)
    events: list[str] = []
    word_level = bool(words) and all(" " not in word.text.strip() for word in words[:20])
    mode = style.mode if word_level else "phrase"
    if mode in {"word", "word_pop"}:
        for word in words:
            text = (
                r"{\fscx65\fscy65"
                r"\t(0,90,\fscx120\fscy120)"
                r"\t(90,155,\fscx94\fscy94)"
                r"\t(155,220,\fscx100\fscy100)"
                r"\fad(35,70)}"
                + _escape(word.text)
            )
            events.extend(_styled_events(word.start, max(word.start + 0.10, word.end),
                                         word.text.strip(), text, style, font, popup=True))
    else:
        for group in _groups(words, style.max_words):
            if not group:
                continue
            lines = _wrap_words(group, font, style)
            plain = r"\N".join(" ".join(item.text.strip() for item in line) for line in lines)
            text = r"\N".join(_phrase_text(line, mode) for line in lines)
            events.extend(_styled_events(group[0].start,
                                         max(group[0].start + 0.15, group[-1].end),
                                         plain, text, style, font))
    destination.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    return destination


def _load_font(style: SubtitleStyle, fonts_dir: Path | None) -> tuple[ImageFont.FreeTypeFont, str]:
    if style.font_file:
        name = Path(style.font_file)
        if name.name != style.font_file or name.suffix.lower() not in {".ttf", ".otf"}:
            raise ValueError("Выберите файл TTF или OTF из папки fonts.")
        if fonts_dir is None or not (fonts_dir / name).is_file():
            raise ValueError(f"Шрифт «{style.font_file}» не найден в папке fonts.")
        font = ImageFont.truetype(str(fonts_dir / name), style.font_size)
        return font, font.getname()[0]
    if fonts_dir and fonts_dir.is_dir():
        for candidate in sorted(fonts_dir.iterdir()):
            if candidate.suffix.lower() not in {".ttf", ".otf"}:
                continue
            try:
                font = ImageFont.truetype(str(candidate), style.font_size)
            except OSError:
                continue
            family, weight = font.getname()
            if style.font_name.lower() in {family.lower(), f"{family} {weight}".lower()}:
                return font, style.font_name
    return ImageFont.load_default(size=style.font_size), style.font_name


def _wrap_words(words: list[Word], font: ImageFont.FreeTypeFont,
                style: SubtitleStyle) -> list[list[Word]]:
    lines: list[list[Word]] = []
    line: list[Word] = []
    available = 1080 - 2 * 70 - 2 * max(0, style.background_padding)
    for word in words:
        candidate = " ".join(item.text.strip() for item in [*line, word])
        if line and font.getlength(candidate) > available:
            lines.append(line)
            line = []
        line.append(word)
    if line:
        lines.append(line)
    return lines


def _styled_events(start: float, end: float, plain: str, rendered: str,
                   style: SubtitleStyle, font: ImageFont.FreeTypeFont,
                   *, popup: bool = False) -> list[str]:
    lines = plain.split(r"\N")
    width = max(float(font.getlength(line)) for line in lines)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    height = line_height * len(lines) + max(0, len(lines) - 1) * 4
    y = (style.margin_v + height / 2 if style.position == "top"
         else 1920 - style.margin_v - height / 2)
    y = max(height / 2 + 20, min(1920 - height / 2 - 20, y))
    x, y = 540, round(y)
    pos = rf"\an5\pos({x},{y})"
    events: list[str] = []
    if style.effect in {"background", "lines", "torn_paper", "paper_letters"} and style.background_opacity > 0:
        padding_x = max(0, style.background_padding)
        padding_y = max(8, round(padding_x * .55))
        factor = 1.2 if popup else 1.0
        alpha = 255 - max(0, min(255, style.background_opacity))
        line_widths = [float(font.getlength(line)) for line in lines]
        for index, line in enumerate(lines):
            if style.effect == "background" and index > 0:
                break
            if style.effect == "background":
                boxes = [(x, y, width * factor, height * factor, padding_x, padding_y)]
            else:
                line_y = round(y - height / 2 + line_height * (index + .5) + index * 4)
                if style.effect == "paper_letters":
                    boxes = []
                    origin = x - line_widths[index] / 2
                    for letter_index, character in enumerate(line):
                        if character.isspace():
                            continue
                        advance = font.getlength(line[:letter_index + 1]) - font.getlength(line[:letter_index])
                        left_edge = origin + font.getlength(line[:letter_index])
                        boxes.append((left_edge + advance / 2, line_y, advance,
                                      line_height, max(2, round(padding_x * .24)),
                                      max(2, round(padding_y * .45))))
                else:
                    boxes = [(x, line_y, line_widths[index] * factor,
                              line_height * factor, padding_x, padding_y)]
            for box_x, box_y, box_w, box_h, pad_x, pad_y in boxes:
                left = round(box_x - box_w / 2 - pad_x)
                right = round(box_x + box_w / 2 + pad_x)
                top = round(box_y - box_h / 2 - pad_y)
                bottom = round(box_y + box_h / 2 + pad_y)
                radius = max(0, min(style.background_corner_radius,
                                    (right - left) // 2, (bottom - top) // 2))
                if style.effect == "torn_paper":
                    vector = _torn_rect(left, top, right, bottom)
                else:
                    vector = _rounded_rect(left, top, right, bottom,
                                           0 if style.effect == "paper_letters" else radius)
                drawing = (rf"{{\an7\pos(0,0)\p1\bord0\shad0"
                           rf"\1c{_ass_color(style.background_color)}\1a&H{alpha:02X}&}}{vector}{{\p0}}")
                events.append(_event(start, end, drawing, layer=0))
    if style.effect == "glow":
        glow = max(1, style.glow_radius)
        alpha = 255 - max(0, min(255, style.glow_opacity))
        glow_tags = (rf"{{{pos}\1a&HFF&\3c{_ass_color(style.glow_color)}"
                     rf"\3a&H{alpha:02X}&\bord{max(2, glow)}\blur{max(1, glow // 2)}\shad0}}")
        events.append(_event(start, end, glow_tags + _escape_lines(plain), layer=0))
    events.append(_event(start, end, f"{{{pos}}}" + rendered, layer=1))
    return events


def _rounded_rect(left: int, top: int, right: int, bottom: int, radius: int) -> str:
    if not radius:
        return f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom}"
    c = round(radius * .5523)
    r = radius
    return (f"m {left+r} {top} l {right-r} {top} "
            f"b {right-r+c} {top} {right} {top+r-c} {right} {top+r} "
            f"l {right} {bottom-r} "
            f"b {right} {bottom-r+c} {right-r+c} {bottom} {right-r} {bottom} "
            f"l {left+r} {bottom} "
            f"b {left+r-c} {bottom} {left} {bottom-r+c} {left} {bottom-r} "
            f"l {left} {top+r} "
            f"b {left} {top+r-c} {left+r-c} {top} {left+r} {top}")


def _torn_rect(left: int, top: int, right: int, bottom: int) -> str:
    # Small, repeatable irregularities mimic the paper edges from Easy Reels.
    step = 24
    top_points = [(left, top)] + [
        (min(right, left + index * step), top + (3 if index % 3 else -3))
        for index in range(1, (right - left) // step + 1)
    ] + [(right, top)]
    bottom_points = [(right, bottom)] + [
        (max(left, right - index * step), bottom + (-3 if index % 3 else 3))
        for index in range(1, (right - left) // step + 1)
    ] + [(left, bottom)]
    coordinates = " ".join(f"{px} {py}" for px, py in top_points[1:] + bottom_points)
    return f"m {left} {top} l {coordinates}"


def _escape_lines(text: str) -> str:
    return r"\N".join(_escape(line) for line in text.split(r"\N"))


def _groups(words: list[Word], max_words: int) -> list[list[Word]]:
    result: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (len(current) >= max_words or word.start - current[-1].end > 0.65):
            result.append(current)
            current = []
        current.append(word)
    if current:
        result.append(current)
    return result


def _phrase_text(group: list[Word], mode: str) -> str:
    if mode == "highlight":
        parts: list[str] = []
        for word in group:
            centiseconds = max(1, int(round((word.end - word.start) * 100)))
            parts.append(rf"{{\kf{centiseconds}}}{_escape(word.text)}")
        return " ".join(parts)
    prefix = r"{\fad(120,120)}" if mode == "fade" else ""
    return prefix + " ".join(_escape(word.text) for word in group)


def _event(start: float, end: float, text: str, *, layer: int = 1) -> str:
    return f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"


def _header(style: SubtitleStyle, font_name: str | None = None) -> str:
    primary = _ass_color(style.primary_color)
    active = _ass_color(style.active_color)
    outline = _ass_color(style.outline_color)
    background = _ass_color(style.background_color, 255)
    border = max(0, style.outline) if style.effect == "outline" else 0
    safe_font = (font_name or style.font_name).replace(",", " ").replace("\n", " ")
    alignment = 8 if style.position == "top" else 2
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{safe_font},{style.font_size},{primary},{active},{outline},{background},-1,0,0,0,100,100,0,0,1,{border},0,{alignment},70,70,{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        value = "FFFFFF"
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f"&H{alpha:02X}{blue}{green}{red}"


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").strip()
