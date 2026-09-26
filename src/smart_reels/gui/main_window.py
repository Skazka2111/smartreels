from __future__ import annotations

from pathlib import Path
import shutil
from typing import Callable

from PySide6.QtCore import QThread, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..models import ApiSettings, ClipCandidate, RenderSettings, SubtitleStyle, format_time, parse_time
from ..pipeline import SmartReelsPipeline
from .workers import TaskWorker


class MainWindow(QMainWindow):
    def __init__(self, project_dir: Path, *, ffmpeg: str, ffprobe: str, fonts_dir: Path | None) -> None:
        super().__init__()
        self.setWindowTitle("Smart Reels Studio — тестовая сборка 9")
        self.resize(1280, 850)
        self.project_dir = project_dir
        self.fonts_dir = fonts_dir or project_dir / "fonts"
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline = SmartReelsPipeline(
            project_dir, ffmpeg=ffmpeg, ffprobe=ffprobe, fonts_dir=fonts_dir
        )
        self.source: Path | None = None
        self.media = None
        self.transcript = None
        self.clips: list[ClipCandidate] = []
        self.thread: QThread | None = None
        self.worker: TaskWorker | None = None
        self._build()

    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        header = QFrame(objectName="Header")
        header_layout = QHBoxLayout(header)
        title_box = QVBoxLayout()
        title = QLabel("Smart Reels Studio", objectName="Title")
        hint = QLabel("Длинное видео → сильные вертикальные ролики", objectName="Hint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        header_info = QVBoxLayout()
        self.source_label = QLabel("Видео не выбрано", objectName="Hint")
        self.source_label.setAlignment(Qt.AlignRight)
        build_label = QLabel("Тестовая сборка 9", objectName="Hint")
        build_label.setAlignment(Qt.AlignRight)
        header_info.addWidget(self.source_label)
        header_info.addWidget(build_label)
        header_layout.addLayout(header_info)
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._source_tab(), "1. Видео")
        self.tabs.addTab(self._api_tab(), "2. Подключения")
        self.tabs.addTab(self._clips_tab(), "3. Фрагменты")
        self.tabs.addTab(self._design_tab(), "4. Оформление")
        self.tabs.addTab(self._log_tab(), "5. Журнал")
        layout.addWidget(self.tabs, 1)

        controls = QHBoxLayout()
        self.analyse_button = QPushButton("Найти фрагменты", objectName="Primary")
        self.analyse_button.clicked.connect(self._analyse)
        self.render_button = QPushButton("Создать выбранные ролики", objectName="Primary")
        self.render_button.clicked.connect(self._render)
        self.render_button.setEnabled(False)
        self.open_results_button = QPushButton("Открыть результаты")
        self.open_results_button.clicked.connect(self._open_results)
        controls.addWidget(self.analyse_button)
        controls.addWidget(self.render_button)
        controls.addWidget(self.open_results_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("Готово к работе", objectName="Hint")
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _source_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        group = QGroupBox("Исходное видео")
        grid = QGridLayout(group)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("MP4, MOV, MKV, M4V, AVI или WEBM")
        choose = QPushButton("Выбрать видео")
        choose.clicked.connect(self._choose_source)
        grid.addWidget(self.source_edit, 0, 0)
        grid.addWidget(choose, 0, 1)
        self.video_info = QLabel(
            "В первой версии используются локальные файлы. Ссылку YouTube добавим после проверки основного монтажа.",
            objectName="Hint",
        )
        self.video_info.setWordWrap(True)
        grid.addWidget(self.video_info, 1, 0, 1, 2)
        layout.addWidget(group)

        search_group = QGroupBox("Количество найденных роликов")
        search_layout = QFormLayout(search_group)
        self.quality_mode = QComboBox()
        self.quality_mode.addItem("Строгий — только самые сильные", "strict")
        self.quality_mode.addItem("Сбалансированный", "balanced")
        self.quality_mode.addItem("Максимальный — больше вариантов", "maximum")
        self.quality_mode.setCurrentIndex(1)
        search_layout.addRow("Режим поиска", self.quality_mode)
        search_layout.addRow(
            QLabel("Жёсткого лимита нет: программа возвращает все неповторяющиеся фрагменты выше порога качества.", objectName="Hint")
        )
        layout.addWidget(search_group)
        layout.addStretch()
        return tab

    def _api_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        transcribe = QGroupBox("Транскрибация")
        form = QFormLayout(transcribe)
        self.transcription_url = QLineEdit("https://api.openai.com/v1")
        self.transcription_model = QLineEdit("whisper-1")
        self.transcription_key = QLineEdit()
        self.transcription_key.setEchoMode(QLineEdit.Password)
        self.transcription_key.setPlaceholderText("Ключ хранится только до закрытия программы")
        form.addRow("API URL", self.transcription_url)
        form.addRow("Модель", self.transcription_model)
        form.addRow("API-ключ", self.transcription_key)
        layout.addWidget(transcribe)

        analysis = QGroupBox("Анализ текста")
        form2 = QFormLayout(analysis)
        self.analysis_url = QLineEdit("https://api.openai.com/v1")
        self.analysis_model = QLineEdit("gpt-4.1-mini")
        self.analysis_key = QLineEdit()
        self.analysis_key.setEchoMode(QLineEdit.Password)
        self.analysis_key.setPlaceholderText("Можно использовать другой совместимый сервис")
        self.same_key = QCheckBox("Использовать тот же ключ")
        self.same_key.toggled.connect(self._copy_key_state)
        form2.addRow("API URL", self.analysis_url)
        form2.addRow("Модель", self.analysis_model)
        form2.addRow("API-ключ", self.analysis_key)
        form2.addRow(self.same_key)
        layout.addWidget(analysis)
        return tab

    def _clips_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Создать", "Оценка", "Начало", "Конец", "Длина", "Название", "Почему выбран"]
        )
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        all_button = QPushButton("Выбрать все")
        none_button = QPushButton("Снять все")
        all_button.clicked.connect(lambda: self._select_all(True))
        none_button.clicked.connect(lambda: self._select_all(False))
        buttons.addWidget(all_button)
        buttons.addWidget(none_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        return tab

    def _design_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        sections = QTabWidget()
        layout.addWidget(sections)

        video_page = QWidget()
        video_layout = QVBoxLayout(video_page)
        captions_page = QWidget()
        captions_layout = QVBoxLayout(captions_page)
        audio_page = QWidget()
        audio_layout = QVBoxLayout(audio_page)

        vertical = QGroupBox("Вертикализация видео")
        vertical_form = QFormLayout(vertical)
        self.video_mode = QComboBox()
        self.video_mode.addItem("Умное кадрирование — следить за героем", "smart_crop")
        self.video_mode.addItem("Вписать видео целиком — цветной фон", "fit_color")
        self.video_mode.addItem("Вписать видео целиком — размытый фон", "fit_blur")
        self.video_background_color = QLineEdit("#101814")
        vertical_form.addRow("Режим", self.video_mode)
        vertical_form.addRow("Цвет фона", self._color_row(self.video_background_color))
        vertical_form.addRow(QLabel("Цвет используется в режиме «цветной фон».", objectName="Hint"))
        video_layout.addWidget(vertical)
        video_layout.addStretch()

        captions = QGroupBox("Субтитры")
        form = QFormLayout(captions)
        self.subtitle_preset = QComboBox()
        self.subtitle_preset.addItem("Свои настройки", None)
        self.subtitle_preset.addItem("Классика: белый текст на тёмном", "background")
        self.subtitle_preset.addItem("По строкам: белый текст на тёмном", "lines")
        self.subtitle_preset.addItem("Рваная бумага: чёрный текст", "torn_paper")
        self.subtitle_preset.addItem("Бумажные буквы: чёрный текст", "paper_letters")
        self.subtitle_preset.addItem("Обводка: белые буквы", "outline")
        self.subtitle_preset.addItem("Неоновое свечение", "glow")
        self.subtitle_preset.addItem("Только текст", "none")
        self.subtitle_mode = QComboBox()
        self.subtitle_mode.addItem("Фразами без анимации", "phrase")
        self.subtitle_mode.addItem("Мягкое появление", "fade")
        self.subtitle_mode.addItem("Подсветка активного слова", "highlight")
        self.subtitle_mode.addItem("По одному слову — pop-up с пружинкой", "word_pop")
        self.subtitle_mode.setCurrentIndex(2)
        self.subtitle_position = QComboBox()
        self.subtitle_position.addItem("Снизу — выше интерфейса Reels", "bottom")
        self.subtitle_position.addItem("Сверху", "top")
        self.font_name = QComboBox()
        self.font_name.setMinimumWidth(230)
        self.font_button = QPushButton("Добавить свой шрифт")
        self.font_button.clicked.connect(self._add_font)
        self.font_preview = QLabel("Пример субтитров: Ваш яркий момент", objectName="Hint")
        self.font_preview.setMinimumHeight(42)
        self.font_name.currentIndexChanged.connect(self._update_font_preview)
        self._refresh_fonts()
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_name, 1)
        font_row.addWidget(self.font_button)
        self.font_size = QSpinBox()
        self.font_size.setRange(24, 120)
        self.font_size.setValue(68)
        self.primary_color = QLineEdit("#FFFFFF")
        self.active_color = QLineEdit("#39FF88")
        self.subtitle_background_color = QLineEdit("#000000")
        self.background_opacity = QSpinBox()
        self.background_opacity.setRange(0, 255)
        self.background_opacity.setValue(115)
        self.subtitle_effect = QComboBox()
        self.subtitle_effect.addItem("Подложка со скруглением", "background")
        self.subtitle_effect.addItem("Подложка под каждой строкой", "lines")
        self.subtitle_effect.addItem("Рваная бумага под строками", "torn_paper")
        self.subtitle_effect.addItem("Бумажные буквы", "paper_letters")
        self.subtitle_effect.addItem("Обводка текста", "outline")
        self.subtitle_effect.addItem("Свечение текста", "glow")
        self.subtitle_effect.addItem("Без подложки и эффектов", "none")
        self.subtitle_padding = QSpinBox()
        self.subtitle_padding.setRange(0, 150)
        self.subtitle_padding.setValue(36)
        self.subtitle_radius = QSpinBox()
        self.subtitle_radius.setRange(0, 100)
        self.subtitle_radius.setValue(24)
        self.outline_color = QLineEdit("#101010")
        self.outline_width = QSpinBox()
        self.outline_width.setRange(0, 30)
        self.outline_width.setValue(6)
        self.glow_color = QLineEdit("#39FF88")
        self.glow_opacity = QSpinBox()
        self.glow_opacity.setRange(0, 255)
        self.glow_opacity.setValue(200)
        self.glow_radius = QSpinBox()
        self.glow_radius.setRange(1, 50)
        self.glow_radius.setValue(18)
        self.subtitle_margin = QSpinBox()
        self.subtitle_margin.setRange(50, 900)
        self.subtitle_margin.setValue(420)
        self.subtitle_preset.currentIndexChanged.connect(self._apply_subtitle_preset)
        form.addRow("Готовый стиль", self.subtitle_preset)
        form.addRow("Анимация", self.subtitle_mode)
        form.addRow("Положение", self.subtitle_position)
        form.addRow("Шрифт", font_row)
        form.addRow("Предпросмотр шрифта", self.font_preview)
        form.addRow("Размер", self.font_size)
        form.addRow("Основной цвет", self._color_row(self.primary_color))
        form.addRow("Активное слово", self._color_row(self.active_color))
        form.addRow("Подложка или эффект", self.subtitle_effect)
        form.addRow("Цвет подложки", self._color_row(self.subtitle_background_color))
        form.addRow("Непрозрачность подложки", self.background_opacity)
        form.addRow("Отступы подложки (бока)", self.subtitle_padding)
        form.addRow("Скругление углов", self.subtitle_radius)
        form.addRow("Цвет обводки", self._color_row(self.outline_color))
        form.addRow("Толщина обводки", self.outline_width)
        form.addRow("Цвет свечения", self._color_row(self.glow_color))
        form.addRow("Сила свечения", self.glow_opacity)
        form.addRow("Радиус свечения", self.glow_radius)
        form.addRow("Отступ от выбранного края", self.subtitle_margin)
        captions_layout.addWidget(captions)
        captions_layout.addStretch()

        audio = QGroupBox("Музыка и конечная заставка")
        form2 = QFormLayout(audio)
        self.music_edit = QLineEdit()
        self.outro_edit = QLineEdit()
        music_row = QHBoxLayout()
        music_row.addWidget(self.music_edit)
        music_button = QPushButton("Выбрать")
        music_button.clicked.connect(lambda: self._choose_optional(self.music_edit, "Музыка (*.mp3 *.wav *.m4a *.aac)"))
        music_row.addWidget(music_button)
        outro_row = QHBoxLayout()
        outro_row.addWidget(self.outro_edit)
        outro_button = QPushButton("Выбрать")
        outro_button.clicked.connect(lambda: self._choose_optional(self.outro_edit, "Видео (*.mp4 *.mov *.m4v *.mkv)"))
        outro_row.addWidget(outro_button)
        self.music_volume = QDoubleSpinBox()
        self.music_volume.setRange(0.0, 0.5)
        self.music_volume.setSingleStep(0.01)
        self.music_volume.setValue(0.10)
        self.quality = QComboBox()
        self.quality.addItem("Стандартное", "standard")
        self.quality.addItem("Высокое", "high")
        form2.addRow("Музыка", music_row)
        form2.addRow("Громкость музыки", self.music_volume)
        form2.addRow("Конечная заставка", outro_row)
        form2.addRow("Качество", self.quality)
        audio_layout.addWidget(audio)
        audio_layout.addStretch()

        sections.addTab(self._scrollable(video_page), "Видео и кадрирование")
        sections.addTab(self._scrollable(captions_page), "Субтитры")
        sections.addTab(self._scrollable(audio_page), "Музыка и заставка")
        return tab

    def _log_tab(self) -> QWidget:
        tab = QWidget()
        log_layout = QVBoxLayout(tab)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log)
        return tab

    def _scrollable(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _color_row(self, target: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(target)
        button = QPushButton("Палитра")
        button.clicked.connect(lambda: self._choose_color(target))
        row.addWidget(button)
        return row

    def _choose_color(self, target: QLineEdit) -> None:
        initial = QColor(target.text().strip())
        if not initial.isValid():
            initial = QColor("#FFFFFF")
        selected = QColorDialog.getColor(initial, self, "Выберите цвет")
        if selected.isValid():
            target.setText(selected.name().upper())

    def _refresh_fonts(self, selected: str = "Montserrat-Bold.ttf") -> None:
        files = sorted((item for item in self.fonts_dir.iterdir()
                        if item.is_file() and item.suffix.lower() in {".ttf", ".otf"}),
                       key=lambda item: item.name.casefold())
        self.font_name.blockSignals(True)
        self.font_name.clear()
        for path in files:
            self.font_name.addItem(path.name, path.name)
        if files:
            index = self.font_name.findData(selected)
            self.font_name.setCurrentIndex(max(0, index))
        self.font_name.blockSignals(False)
        self._update_font_preview()

    def _apply_subtitle_preset(self, _index: int = -1) -> None:
        effect = self.subtitle_preset.currentData()
        if not effect:
            return
        index = self.subtitle_effect.findData(effect)
        if index >= 0:
            self.subtitle_effect.setCurrentIndex(index)
        self.primary_color.setText("#111111" if effect in {"torn_paper", "paper_letters"} else "#FFFFFF")
        self.subtitle_background_color.setText("#FFFFFF" if effect in {"torn_paper", "paper_letters"} else "#111111")
        self.background_opacity.setValue(245 if effect in {"torn_paper", "paper_letters"} else 230)
        self.subtitle_padding.setValue(22 if effect in {"lines", "torn_paper", "paper_letters"} else 36)
        self.subtitle_radius.setValue(12 if effect == "lines" else 24)
        self.outline_color.setText("#000000")
        self.outline_width.setValue(6 if effect == "outline" else 0)
        self.glow_color.setText("#39FF88")
        self.glow_opacity.setValue(205)
        self.glow_radius.setValue(18)

    def _update_font_preview(self, _index: int = -1) -> None:
        name = self.font_name.currentData()
        if not name:
            self.font_preview.setText("Добавьте шрифт TTF или OTF в папку fonts.")
            return
        font_id = QFontDatabase.addApplicationFont(str(self.fonts_dir / name))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            sample = QFont(families[0])
            sample.setPixelSize(26)
            self.font_preview.setFont(sample)
            self.font_preview.setText("Пример субтитров: Ваш яркий момент")
        else:
            self.font_preview.setText("Файл шрифта не поддерживается. Выберите другой.")

    def _add_font(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Добавить свой шрифт", "", "Шрифты (*.ttf *.otf)")
        if not filename:
            return
        source = Path(filename)
        destination = self.fonts_dir / source.name
        try:
            if source.resolve() != destination.resolve():
                counter = 2
                while destination.exists():
                    destination = self.fonts_dir / f"{source.stem}_{counter}{source.suffix.lower()}"
                    counter += 1
                shutil.copy2(source, destination)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось добавить шрифт", str(exc))
            return
        self._refresh_fonts(destination.name)

    def _choose_source(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Выберите длинное видео", "", "Видео (*.mp4 *.mov *.mkv *.m4v *.avi *.webm)"
        )
        if filename:
            self.source_edit.setText(filename)
            self.source_label.setText(Path(filename).name)

    def _choose_optional(self, target: QLineEdit, file_filter: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Выберите файл", "", file_filter)
        if filename:
            target.setText(filename)

    def _copy_key_state(self, checked: bool) -> None:
        if checked:
            self.analysis_key.setText(self.transcription_key.text())
        self.analysis_key.setEnabled(not checked)

    def _api_settings(self) -> ApiSettings:
        analysis_key = self.transcription_key.text() if self.same_key.isChecked() else self.analysis_key.text()
        return ApiSettings(
            transcription_base_url=self.transcription_url.text().strip(),
            transcription_model=self.transcription_model.text().strip(),
            transcription_key=self.transcription_key.text().strip(),
            analysis_base_url=self.analysis_url.text().strip(),
            analysis_model=self.analysis_model.text().strip(),
            analysis_key=analysis_key.strip(),
        )

    def _analyse(self) -> None:
        source = Path(self.source_edit.text().strip())
        if not source.is_file():
            QMessageBox.warning(self, "Видео", "Сначала выберите существующий видеофайл.")
            return
        api = self._api_settings()
        self.source = source
        mode = self.quality_mode.currentData()
        self._start_task(
            lambda progress: self.pipeline.analyse(source, api, quality_mode=mode, progress=progress),
            self._analysis_ready,
        )

    def _analysis_ready(self, result: object) -> None:
        self.media, self.transcript, self.clips = result
        self.video_info.setText(
            f"{self.media.width}×{self.media.height}, {format_time(self.media.duration)}, "
            f"найдено фрагментов: {len(self.clips)}"
        )
        self._fill_table()
        self.render_button.setEnabled(bool(self.clips))
        self.tabs.setCurrentIndex(2)
        if not self.clips:
            QMessageBox.information(self, "Анализ завершён", "Подходящих фрагментов выше выбранного порога не найдено.")

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.clips))
        for row, clip in enumerate(self.clips):
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            use.setCheckState(Qt.Checked if clip.selected else Qt.Unchecked)
            self.table.setItem(row, 0, use)
            self.table.setItem(row, 1, QTableWidgetItem(str(clip.score)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{clip.start:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{clip.end:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{clip.duration:.1f} сек"))
            self.table.setItem(row, 5, QTableWidgetItem(clip.title))
            self.table.setItem(row, 6, QTableWidgetItem(clip.reason))

    def _select_all(self, selected: bool) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if selected else Qt.Unchecked)

    def _sync_clips_from_table(self) -> bool:
        try:
            for row, clip in enumerate(self.clips):
                clip.selected = self.table.item(row, 0).checkState() == Qt.Checked
                clip.start = parse_time(self.table.item(row, 2).text())
                clip.end = parse_time(self.table.item(row, 3).text())
                if clip.end <= clip.start:
                    raise ValueError(f"В строке {row + 1} конец должен быть позже начала.")
        except ValueError as exc:
            QMessageBox.warning(self, "Тайминги", str(exc))
            return False
        return True

    def _render(self) -> None:
        if not self.source or not self.media or not self.transcript or not self._sync_clips_from_table():
            return
        if not any(item.selected for item in self.clips):
            QMessageBox.warning(self, "Ролики", "Выберите хотя бы один фрагмент.")
            return
        font_file = self.font_name.currentData()
        font_id = QFontDatabase.addApplicationFont(str(self.fonts_dir / font_file)) if font_file else -1
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if not families:
            QMessageBox.warning(self, "Шрифт", "Выберите работающий шрифт из папки fonts.")
            return
        font_family = families[0]
        subtitle = SubtitleStyle(
            mode=self.subtitle_mode.currentData(),
            font_name=font_family,
            font_file=font_file,
            font_size=self.font_size.value(),
            primary_color=self.primary_color.text().strip(),
            active_color=self.active_color.text().strip(),
            background_color=self.subtitle_background_color.text().strip(),
            background_opacity=self.background_opacity.value(),
            effect=self.subtitle_effect.currentData(),
            background_padding=self.subtitle_padding.value(),
            background_corner_radius=self.subtitle_radius.value(),
            outline_color=self.outline_color.text().strip(),
            outline=self.outline_width.value(),
            glow_color=self.glow_color.text().strip(),
            glow_opacity=self.glow_opacity.value(),
            glow_radius=self.glow_radius.value(),
            position=self.subtitle_position.currentData(),
            margin_v=self.subtitle_margin.value(),
        )
        settings = RenderSettings(
            output_dir=self.pipeline.output_dir,
            subtitle=subtitle,
            music_file=Path(self.music_edit.text()) if self.music_edit.text().strip() else None,
            music_volume=self.music_volume.value(),
            outro_file=Path(self.outro_edit.text()) if self.outro_edit.text().strip() else None,
            video_mode=self.video_mode.currentData(),
            background_color=self.video_background_color.text().strip(),
            quality=self.quality.currentData(),
        )
        self._start_task(
            lambda progress: self.pipeline.render_all(
                self.source, self.media, self.transcript, self.clips, settings, progress=progress
            ),
            self._render_ready,
        )

    def _render_ready(self, result: object) -> None:
        paths = list(result)
        QMessageBox.information(self, "Готово", f"Создано роликов: {len(paths)}\n\n{self.pipeline.output_dir}")
        self._open_results()

    def _start_task(self, task: Callable, on_success: Callable[[object], None]) -> None:
        if self.thread and self.thread.isRunning():
            return
        self.analyse_button.setEnabled(False)
        self.render_button.setEnabled(False)
        self.progress.setValue(0)
        self.thread = QThread(self)
        self.worker = TaskWorker(task)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._task_progress)
        self.worker.finished.connect(on_success)
        self.worker.finished.connect(self._task_done)
        self.worker.failed.connect(self._task_failed)
        self.worker.failed.connect(lambda *_: self._task_done())
        self.thread.start()

    def _task_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, percent)))
        self.status.setText(message)
        self.log.appendPlainText(message)

    def _task_done(self, *_args) -> None:
        self.analyse_button.setEnabled(True)
        self.render_button.setEnabled(bool(self.clips))
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
        self.worker = None
        self.thread = None

    def _task_failed(self, message: str, technical: str) -> None:
        self.status.setText("Ошибка")
        self.log.appendPlainText(technical)
        QMessageBox.critical(self, "Не удалось выполнить операцию", message)

    def _open_results(self) -> None:
        self.pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pipeline.output_dir.resolve())))
