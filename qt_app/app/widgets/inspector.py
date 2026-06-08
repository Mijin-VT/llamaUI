"""Right-side inspector panel.

Phase 8 note: this panel must not fabricate runtime state. It stays generic until
it is explicitly wired to a page/controller that owns real data.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from .. import theme
from .cards import Chip, MonoLog


class Inspector(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CardAlt")
        self.setFixedWidth(theme.INSPECTOR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        self._title = QLabel("Inspector", self)
        self._title.setObjectName("CardTitle")
        self._layout.addWidget(self._title)

        status_card = QFrame(self)
        status_card.setObjectName("Card")
        s_layout = QVBoxLayout(status_card)
        s_layout.setContentsMargins(12, 12, 12, 12)
        s_layout.setSpacing(6)
        self._chip = Chip("No live runtime bound", "muted", status_card)
        s_layout.addWidget(self._chip)
        self._line1 = QLabel("Select a page or model to inspect real details.", status_card)
        self._line1.setObjectName("Muted")
        s_layout.addWidget(self._line1)
        self._line2 = QLabel("Runtime status is shown on the Run page.", status_card)
        self._line2.setObjectName("Muted")
        s_layout.addWidget(self._line2)
        self._layout.addWidget(status_card)

        cmd_card = QFrame(self)
        cmd_card.setObjectName("InsetRaised")
        c_layout = QVBoxLayout(cmd_card)
        c_layout.setContentsMargins(10, 10, 10, 10)
        c_layout.setSpacing(4)
        self._command = MonoLog(cmd_card)
        self._command.append_line("No command preview available here.")
        c_layout.addWidget(self._command)
        self._layout.addWidget(cmd_card)
        self._layout.addStretch(1)

    def update_details(self, title: str, chip_text: str, chip_style: str, line1: str, line2: str, command_lines: list[str] | None = None) -> None:
        self._title.setText(title)
        self._chip.setText(chip_text)
        self._chip.set_style(chip_style)
        self._line1.setText(line1)
        self._line2.setText(line2)
        while self._command._layout.count():
            item = self._command._layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        for line in (command_lines or ["No command preview available here."]):
            self._command.append_line(line)
        return

    def set_context(self, title: str, chip_text: str, chip_style: str) -> None:
        self._title.setText(title)
        self._chip.setText(chip_text)
        self._chip.set_style(chip_style)
