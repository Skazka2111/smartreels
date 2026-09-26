from __future__ import annotations

import traceback
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot


class TaskWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str, str)

    def __init__(self, task: Callable[[Callable[[int, str], None]], object]) -> None:
        super().__init__()
        self.task = task

    @Slot()
    def run(self) -> None:
        try:
            result = self.task(lambda percent, message: self.progress.emit(percent, message))
        except Exception as exc:
            technical = getattr(exc, "technical_detail", None) or traceback.format_exc()
            self.failed.emit(str(exc), technical)
        else:
            self.finished.emit(result)
