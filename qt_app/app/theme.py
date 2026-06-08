"""Color tokens, spacing, typography, and the global QSS stylesheet.

Centralizing the visual system here means the rest of the app can stay focused
on behavior. Colors match the KDE-friendly dark mockups in
``plans/mockup-run-settings.svg`` and ``plans/mockup-discover-library.svg``.
"""
from __future__ import annotations

from dataclasses import dataclass


# --- Color tokens -------------------------------------------------------------
# Surface scale: deeper tones recede, lighter tones carry content.
BG_APP = "#111827"        # window background
BG_SIDEBAR = "#0b1220"    # left rail
BG_HEADER = "#182235"     # top bar
BG_PANEL = "#1e293b"      # cards / panels
BG_PANEL_ALT = "#162033"  # inspector
BG_RAISED = "#0f172a"     # nested blocks, command preview
BG_INSET = "#020617"      # logs, deepest inset

BORDER = "#334155"
BORDER_SOFT = "#1f2a3d"

FG_PRIMARY = "#f8fafc"
FG_SECONDARY = "#cbd5e1"
FG_MUTED = "#94a3b8"
FG_FAINT = "#64748b"

ACCENT = "#6d28d9"         # primary action (violet)
ACCENT_HOVER = "#7c3aed"
ACCENT_PRESSED = "#5b21b6"
ACCENT_SOFT = "#312e81"    # pill/chip backgrounds

SUCCESS = "#16a34a"
SUCCESS_SOFT = "#22c55e"
WARNING = "#eab308"
DANGER = "#991b1b"
DANGER_HOVER = "#b91c1c"

SIDEBAR_WIDTH = 220
INSPECTOR_WIDTH = 320
HEADER_HEIGHT = 64


@dataclass(frozen=True)
class FontSpec:
    family: str
    base_pt: int


FONT_UI = FontSpec("Inter, Segoe UI, Cantarell, sans-serif", 10)
FONT_MONO = FontSpec("JetBrains Mono, Consolas, monospace", 10)


def font_css(spec: FontSpec) -> str:
    return f'font-family: "{spec.family}"; font-size: {spec.base_pt}pt;'


# --- Stylesheet ---------------------------------------------------------------
# Built once at import; the app sets it via QApplication.setStyleSheet.

def build_stylesheet() -> str:
    f_ui = font_css(FONT_UI)
    f_mono = font_css(FONT_MONO)

    return f"""
    QWidget {{
        {f_ui}
        color: {FG_PRIMARY};
        background-color: {BG_APP};
    }}

    QMainWindow {{
        background-color: {BG_APP};
    }}

    /* --- Sidebar --- */
    QFrame#Sidebar {{
        background-color: {BG_SIDEBAR};
        border-right: 1px solid {BORDER_SOFT};
    }}
    QLabel#SidebarBrand {{
        color: {ACCENT_SOFT};
        font-size: 22pt;
        font-weight: 700;
        padding: 18px 24px 12px 24px;
        letter-spacing: 0.5px;
    }}
    QPushButton#NavItem {{
        text-align: left;
        padding: 10px 24px;
        border: none;
        background: transparent;
        color: {FG_SECONDARY};
        font-size: 11pt;
        border-left: 3px solid transparent;
    }}
    QPushButton#NavItem:hover {{
        background-color: rgba(109, 40, 217, 0.08);
        color: {FG_PRIMARY};
    }}
    QPushButton#NavItem:checked {{
        color: {FG_PRIMARY};
        font-weight: 700;
        background-color: rgba(109, 40, 217, 0.14);
        border-left: 3px solid {ACCENT};
    }}

    /* --- Header bar --- */
    QFrame#Header {{
        background-color: {BG_HEADER};
        border-bottom: 1px solid {BORDER_SOFT};
    }}
    QLabel#HeaderTitle {{
        color: {FG_PRIMARY};
        font-size: 14pt;
        font-weight: 700;
        padding-left: 16px;
    }}
    QLabel#HeaderSubtitle {{
        color: {FG_MUTED};
        font-size: 9pt;
        padding-left: 16px;
    }}

    /* --- Cards / panels --- */
    QFrame#Card {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}
    QFrame#CardAlt {{
        background-color: {BG_PANEL_ALT};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}
    QFrame#Inset {{
        background-color: {BG_INSET};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    QFrame#InsetRaised {{
        background-color: {BG_RAISED};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    QLabel#CardTitle {{
        color: {FG_PRIMARY};
        font-size: 12pt;
        font-weight: 700;
    }}
    QLabel#CardSubtitle {{
        color: {FG_MUTED};
        font-size: 9pt;
    }}
    QLabel#FieldLabel {{
        color: #c4b5fd;
        font-size: 8pt;
    }}
    QLabel#FieldValue {{
        color: {FG_PRIMARY};
        font-size: 13pt;
        font-weight: 700;
    }}
    QLabel#Muted {{
        color: {FG_MUTED};
    }}
    QLabel#Mono {{
        {f_mono}
        color: {FG_MUTED};
    }}

    /* --- Inspector chips --- */
    QLabel#Chip {{
        color: {FG_PRIMARY};
        font-size: 9pt;
        font-weight: 700;
        padding: 2px 10px;
        border-radius: 10px;
    }}
    QLabel#ChipSuccess {{ background-color: {SUCCESS_SOFT}; color: #052e16; }}
    QLabel#ChipWarning {{ background-color: {WARNING}; color: #422006; }}
    QLabel#ChipAccent  {{ background-color: {ACCENT_SOFT}; color: {FG_PRIMARY}; }}
    QLabel#ChipMuted   {{ background-color: {BG_RAISED}; color: {FG_SECONDARY}; }}

    /* --- Buttons --- */
    QPushButton {{
        background-color: {ACCENT};
        color: white;
        border: none;
        border-radius: 7px;
        padding: 8px 18px;
        font-size: 10pt;
        font-weight: 600;
    }}
    QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}
    QPushButton:pressed {{ background-color: {ACCENT_PRESSED}; }}
    QPushButton:disabled {{ background-color: {BG_RAISED}; color: {FG_FAINT}; }}

    QPushButton[variant="secondary"] {{
        background-color: {BG_RAISED};
        color: {FG_SECONDARY};
        border: 1px solid {BORDER};
    }}
    QPushButton[variant="secondary"]:hover {{
        background-color: #1e293b;
        color: {FG_PRIMARY};
    }}
    QPushButton[variant="danger"] {{
        background-color: {DANGER};
    }}
    QPushButton[variant="danger"]:hover {{
        background-color: {DANGER_HOVER};
    }}
    QPushButton[variant="success"] {{
        background-color: {SUCCESS};
    }}
    QPushButton[variant="success"]:hover {{
        background-color: #15803d;
    }}

    /* --- Search input --- */
    QLineEdit {{
        background-color: {BG_RAISED};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 14px;
        color: {FG_PRIMARY};
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus {{ border: 1px solid {ACCENT}; }}

    QComboBox, QSpinBox {{
        background-color: {BG_RAISED};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 6px 10px;
        color: {FG_PRIMARY};
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_PANEL};
        color: {FG_PRIMARY};
        selection-background-color: {ACCENT};
    }}

    QPlainTextEdit, QTextBrowser {{
        background-color: {BG_INSET};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px;
        color: {FG_SECONDARY};
    }}

    QTableWidget {{
        background-color: {BG_INSET};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER_SOFT};
        selection-background-color: rgba(109, 40, 217, 0.24);
        selection-color: {FG_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: {BG_RAISED};
        color: {FG_MUTED};
        padding: 6px 8px;
        border: none;
        border-right: 1px solid {BORDER_SOFT};
        border-bottom: 1px solid {BORDER_SOFT};
    }}

    /* --- Filter pills --- */
    QPushButton#FilterPill {{
        background-color: {BG_RAISED};
        color: {FG_SECONDARY};
        border-radius: 14px;
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* --- Combo box --- */
    QComboBox {{
        background-color: {BG_RAISED};
        border: 1px solid {BORDER};
        border-radius: 7px;
        padding: 6px 12px;
        color: {FG_PRIMARY};
        min-width: 80px;
    }}
    QComboBox:hover {{ border: 1px solid {ACCENT}; }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {FG_MUTED};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        color: {FG_PRIMARY};
        selection-background-color: {ACCENT};
        selection-color: {FG_PRIMARY};
        outline: none;
    }}

    /* --- Spin box --- */
    QSpinBox {{
        background-color: {BG_RAISED};
        border: 1px solid {BORDER};
        border-radius: 7px;
        padding: 6px 10px;
        color: {FG_PRIMARY};
    }}
    QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: transparent;
        border: none;
        width: 18px;
    }}
    QSpinBox::up-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {FG_MUTED};
    }}
    QSpinBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {FG_MUTED};
    }}

    /* --- Plain text edit / log blocks --- */
    QPlainTextEdit, QTextEdit {{
        {f_mono}
        background-color: {BG_INSET};
        border: 1px solid {BORDER};
        border-radius: 8px;
        color: {FG_SECONDARY};
        padding: 8px;
        selection-background-color: {ACCENT};
    }}

    /* --- Table widget --- */
    QTableWidget {{
        background-color: {BG_RAISED};
        alternate-background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER_SOFT};
        color: {FG_PRIMARY};
    }}
    QTableWidget::item {{
        padding: 4px 8px;
    }}
    QTableWidget::item:selected {{
        background-color: {ACCENT};
    }}
    QHeaderView::section {{
        background-color: {BG_PANEL};
        color: {FG_MUTED};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px 10px;
        font-size: 9pt;
        font-weight: 600;
    }}

    /* --- Tooltip --- */
    QToolTip {{
        background-color: {BG_RAISED};
        color: {FG_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 9pt;
    }}

    /* --- Top page header --- */
    QFrame#TopHeader {{
        background-color: {BG_HEADER};
        border-bottom: 1px solid {BORDER_SOFT};
    }}
    QLabel#PageTitle {{
        color: {FG_PRIMARY};
        font-size: 16pt;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}
    QFrame#CenterColumn {{
        background-color: {BG_APP};
    }}
    QWidget#PageBody {{
        background-color: {BG_APP};
    }}
    """


def apply_palette(app) -> None:
    """Set a dark palette that matches the QSS for native-rendered widgets.

    QSS does not style every native surface (e.g. focus, tooltips, menus),
    so we set the default palette first and let QSS override per-control.
    """
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG_APP))
    p.setColor(QPalette.ColorRole.WindowText, QColor(FG_PRIMARY))
    p.setColor(QPalette.ColorRole.Base, QColor(BG_RAISED))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_PANEL))
    p.setColor(QPalette.ColorRole.Text, QColor(FG_PRIMARY))
    p.setColor(QPalette.ColorRole.Button, QColor(BG_PANEL))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(FG_PRIMARY))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(FG_PRIMARY))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(FG_MUTED))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_RAISED))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(FG_PRIMARY))
    app.setPalette(p)
