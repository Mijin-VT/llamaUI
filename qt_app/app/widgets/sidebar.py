"""Left navigation rail with brand and selectable nav items."""
from __future__ import annotations
from enum import Enum
from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from .. import theme


class NavItemId(str, Enum):
    """Stable identifiers for navigation destinations.

    Enum values are stored as strings so they can be persisted in config
    later without needing to translate integer indexes.
    """

    LIBRARY = "library"
    DISCOVER = "discover"
    RUN = "run"
    SETTINGS = "settings"
    DIAGNOSTICS = "diagnostics"


_NAV_LABELS: Dict[NavItemId, str] = {
    NavItemId.LIBRARY: "Library",
    NavItemId.DISCOVER: "Discover",
    NavItemId.RUN: "Run",
    NavItemId.SETTINGS: "Settings",
    NavItemId.DIAGNOSTICS: "Diagnostics",
}


class Sidebar(QFrame):
    """Left rail that emits a :class:`NavItemId` when an item is selected."""

    navigated = Signal(object)  # emits NavItemId

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(theme.SIDEBAR_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("llamaUI", self)
        brand.setObjectName("SidebarBrand")
        layout.addWidget(brand)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: Dict[NavItemId, QPushButton] = {}

        for item_id in NavItemId:
            btn = QPushButton(_NAV_LABELS[item_id], self)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self._group.addButton(btn)
            self._buttons[item_id] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

        self._status = QFrame(self)
        self._status.setObjectName("SidebarStatus")
        status_layout = QVBoxLayout(self._status)
        status_layout.setContentsMargins(14, 10, 14, 12)
        status_layout.setSpacing(4)
        self._status_title = QLabel("Run", self._status)
        self._status_title.setObjectName("SidebarStatusTitle")
        self._status_title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        status_layout.addWidget(self._status_title)
        self._status_chip = QLabel("stopped", self._status)
        self._status_chip.setObjectName("SidebarStatusChip")
        status_layout.addWidget(self._status_chip)
        self._status_line1 = QLabel("No model selected", self._status)
        self._status_line1.setObjectName("Muted")
        self._status_line1.setWordWrap(True)
        status_layout.addWidget(self._status_line1)
        self._status_line2 = QLabel("endpoint=http://127.0.0.1:8080", self._status)
        self._status_line2.setObjectName("Muted")
        self._status_line2.setWordWrap(True)
        status_layout.addWidget(self._status_line2)
        layout.addWidget(self._status)

        for item_id, btn in self._buttons.items():
            btn.clicked.connect(lambda _checked=False, i=item_id: self._on_clicked(i))

    def _on_clicked(self, item_id: NavItemId) -> None:
        self.navigated.emit(item_id)

    def set_active(self, item_id: NavItemId) -> None:
        """Mark ``item_id`` as the currently selected page."""
        btn = self._buttons[item_id]
        btn.setChecked(True)

    def update_details(self, title: str, chip_text: str, chip_style: str, line1: str, line2: str, command_lines: list[str] | None = None) -> None:
        self._status_title.setText(title or "Run")
        self._status_chip.setText(chip_text or "—")
        self._status_chip.setProperty("chipStyle", chip_style or "muted")
        self._status_chip.style().unpolish(self._status_chip)
        self._status_chip.style().polish(self._status_chip)
        self._status_line1.setText(line1 or "")
        self._status_line2.setText(line2 or "")


