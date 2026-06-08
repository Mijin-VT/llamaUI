"""Reusable card primitives: titles, field tiles, status chips, log blocks."""
from __future__ import annotations

from typing import Literal, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

ChipStyle = Literal["success", "warning", "accent", "muted"]


class Card(QFrame):
    """A bordered, rounded panel — the base building block for content."""

    def __init__(self, parent: Optional[QFrame] = None, *, alt: bool = False):
        super().__init__(parent)
        self.setObjectName("CardAlt" if alt else "Card")


class CardTitle(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("CardTitle")


class FieldTile(QFrame):
    """A small bordered tile showing a label (e.g. ``--ctx-size``) and value."""

    def __init__(self, label: str, value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("InsetRaised")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(64)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._label = QLabel(label, self)
        self._label.setObjectName("FieldLabel")
        layout.addWidget(self._label)

        self._value = QLabel(value, self)
        self._value.setObjectName("FieldValue")
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class Chip(QLabel):
    """A small colored status pill (GPU likely, Partial GPU, ...)."""

    _STYLE_OBJECT: dict[ChipStyle, str] = {
        "success": "ChipSuccess",
        "warning": "ChipWarning",
        "accent": "ChipAccent",
        "muted": "ChipMuted",
    }

    def __init__(self, text: str, style: ChipStyle = "muted", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self._current_style: ChipStyle = "muted"
        self.set_style(style)

    def set_style(self, style: ChipStyle) -> None:
        # Remove the previous object name suffix by resetting objectName, then
        # set the new style object name. QSS re-evaluates on objectName change.
        self.setObjectName("Chip")
        self._current_style = style
        self.setObjectName(self._STYLE_OBJECT.get(style, "ChipMuted"))
        # Force re-polish so the QSS rule applies.
        self.style().polish(self)


class MonoLog(QFrame):
    """A monospaced, preformatted block used for command previews and logs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Inset")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(2)
        self._layout.setAlignment(Qt.AlignTop)

    def append_line(self, text: str) -> None:
        line = QLabel(text, self)
        line.setObjectName("Mono")
        line.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._layout.addWidget(line)
