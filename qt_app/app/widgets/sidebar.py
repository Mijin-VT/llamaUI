"""Left navigation rail with brand and selectable nav items."""
from __future__ import annotations
from enum import Enum
from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
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
    PROFILES = "profiles"
    SETTINGS = "settings"
    DIAGNOSTICS = "diagnostics"


_NAV_LABELS: Dict[NavItemId, str] = {
    NavItemId.LIBRARY: "Library",
    NavItemId.DISCOVER: "Discover",
    NavItemId.RUN: "Run",
    NavItemId.PROFILES: "Profiles",
    NavItemId.SETTINGS: "Settings",
    NavItemId.DIAGNOSTICS: "Diagnostics",
}


class Sidebar(QFrame):
    """Left rail that emits a :class:`NavItemId` when an item is selected."""

    navigated = Signal(object)  # emits NavItemId

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(theme.SIDEBAR_WIDTH)

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

        for item_id, btn in self._buttons.items():
            btn.clicked.connect(lambda _checked=False, i=item_id: self._on_clicked(i))

    def _on_clicked(self, item_id: NavItemId) -> None:
        self.navigated.emit(item_id)

    def set_active(self, item_id: NavItemId) -> None:
        """Mark ``item_id`` as the currently selected page."""
        btn = self._buttons[item_id]
        btn.setChecked(True)


