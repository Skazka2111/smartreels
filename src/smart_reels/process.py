from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .errors import SmartReelsError


def hidden_process_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    if progress:
        progress(" ".join(str(item) for item in command[:4]))
    try:
        completed = subprocess.run(
            [str(item) for item in command],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **hidden_process_kwargs(),
        )
    except FileNotFoundError as exc:
        raise SmartReelsError(f"Не найдена программа: {command[0]}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SmartReelsError(_concise_process_error(detail), technical_detail=detail)
    return completed


def _concise_process_error(detail: str) -> str:
    if not detail.strip():
        return "Внешняя программа завершилась с ошибкой."
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    error_pattern = re.compile(
        r"error|failed|invalid|unable|not found|no such|conversion failed|\bunknown\b",
        re.IGNORECASE,
    )
    selected = [line for line in lines if error_pattern.search(line)]
    if not selected:
        selected = lines[-6:]
    selected = selected[-8:]
    compact: list[str] = []
    for line in selected:
        if len(line) > 500:
            line = line[:320] + " … " + line[-140:]
        compact.append(line)
    result = "\n".join(compact)
    if len(result) > 1800:
        result = result[:1800] + "…"
    return result or "Внешняя программа завершилась с ошибкой."
