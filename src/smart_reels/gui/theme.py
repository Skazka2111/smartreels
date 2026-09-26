BACKGROUND = "#0B0F0D"
PANEL = "#141A17"
ACCENT = "#39FF88"
TEXT = "#F3F7F4"
MUTED = "#8B9991"
ERROR = "#FF5C6C"

STYLESHEET = f"""
QWidget {{ background:{BACKGROUND}; color:{TEXT}; font-family:'Segoe UI','Inter','Arial'; font-size:14px; }}
QMainWindow, QDialog {{ background:{BACKGROUND}; }}
QLabel {{ background:transparent; }}
QLabel#Title {{ font-size:27px; font-weight:800; }}
QLabel#Hint {{ color:{MUTED}; }}
QFrame#Header, QGroupBox {{ background:{PANEL}; border:1px solid #29382F; border-radius:14px; }}
QGroupBox {{ margin-top:13px; padding:16px 12px 12px; font-weight:700; }}
QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 7px; color:{ACCENT}; }}
QPushButton {{ min-height:42px; padding:0 17px; border-radius:11px; border:1px solid #35483D; background:#19211D; font-weight:700; }}
QPushButton:hover {{ border-color:{ACCENT}; background:#1D2A23; }}
QPushButton:disabled {{ color:#59645E; border-color:#252E29; background:#111613; }}
QPushButton#Primary {{ color:#07110B; background:{ACCENT}; border-color:{ACCENT}; font-weight:900; }}
QPushButton#Danger {{ color:{ERROR}; border-color:#71313B; background:#261519; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height:40px; padding:0 11px; border-radius:10px; border:1px solid #35483D; background:#0F1511; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color:{ACCENT}; }}
QTableWidget {{ background:#0F1511; alternate-background-color:#141C17; border:1px solid #304137; gridline-color:#29372F; selection-background-color:#235F3B; }}
QTableWidget::item {{ padding:6px; }}
QHeaderView::section {{ background:#19211D; border:0; border-right:1px solid #304137; border-bottom:1px solid #304137; padding:8px; font-weight:700; }}
QTabWidget::pane {{ border:1px solid #29382F; border-radius:12px; }}
QTabBar::tab {{ min-width:130px; min-height:40px; padding:0 15px; margin-right:4px; background:{PANEL}; color:{MUTED}; border:1px solid #2D3B33; border-bottom:0; border-top-left-radius:9px; border-top-right-radius:9px; }}
QTabBar::tab:selected {{ color:{ACCENT}; background:#102219; border-color:#2E6D48; }}
QProgressBar {{ min-height:14px; max-height:14px; border:0; border-radius:7px; background:#202923; color:transparent; }}
QProgressBar::chunk {{ border-radius:7px; background:{ACCENT}; }}
QPlainTextEdit {{ background:#0F1511; border:1px solid #304137; border-radius:10px; color:{MUTED}; }}
QCheckBox {{ spacing:8px; }}
QSlider::groove:horizontal {{ height:7px; border-radius:3px; background:#26332C; }}
QSlider::sub-page:horizontal {{ background:#14C96C; border-radius:3px; }}
QSlider::handle:horizontal {{ width:18px; margin:-6px 0; border-radius:9px; background:{ACCENT}; }}
"""

