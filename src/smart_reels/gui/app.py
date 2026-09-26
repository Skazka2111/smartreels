from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import STYLESHEET


PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def default_project_root() -> Path:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            for parent in executable.parents:
                if parent.suffix.casefold() == ".app":
                    return parent.parent
        return executable.parent
    return Path.cwd() / "Smart_Reels_Project"


def bundled_tool(name: str) -> str:
    executable_name = f"{name}.exe" if sys.platform == "win32" else name
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        bundle_root = Path(getattr(sys, "_MEIPASS", executable.parent)).resolve()
        candidates = [
            executable.parent / executable_name,
            bundle_root / executable_name,
            bundle_root / "_internal" / executable_name,
        ]
        if sys.platform == "darwin":
            for parent in executable.parents:
                if parent.suffix.casefold() == ".app":
                    candidates.extend([
                        parent / "Contents" / "MacOS" / executable_name,
                        parent / "Contents" / "Frameworks" / executable_name,
                        parent / "Contents" / "Resources" / executable_name,
                    ])
                    break
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return executable_name


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    default_root = default_project_root()
    default_fonts = default_root / "fonts"
    if not getattr(sys, "frozen", False) and not default_fonts.exists():
        source_fonts = PACKAGE_ROOT.parents[1] / "portable_template" / "fonts"
        if source_fonts.is_dir():
            default_fonts = source_fonts
    result.add_argument("--project", default=str(default_root))
    result.add_argument("--ffmpeg", default=bundled_tool("ffmpeg"))
    result.add_argument("--ffprobe", default=bundled_tool("ffprobe"))
    result.add_argument("--fonts", default=str(default_fonts))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("Smart Reels Studio")
    application.setOrganizationName("ProAI Studio")
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 10))
    application.setStyleSheet(STYLESHEET)
    icon = PACKAGE_ROOT / "assets" / "icon.png"
    if icon.is_file():
        application.setWindowIcon(QIcon(str(icon)))
    project = Path(args.project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    window = MainWindow(
        project,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        fonts_dir=Path(args.fonts) if args.fonts else None,
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
