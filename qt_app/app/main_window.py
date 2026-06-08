from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from llama_data import ConfigStore, LibraryStore, ProfileStore

from .pages.diagnostics import DiagnosticsPage
from .pages.discover import DiscoverPage
from .pages.library import LibraryPage
from .pages.profiles import ProfilesPage
from .pages.run import RunPage
from .pages.settings import SettingsPage
from .widgets.inspector import Inspector
from .widgets.sidebar import NavItemId, Sidebar

class MainWindow(QMainWindow):
    """Native Qt shell for the rebuilt llamaUI app."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("llamaUI")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 720)

        root = QWidget(self)
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar(root)
        self.sidebar.navigated.connect(self.navigate)
        root_layout.addWidget(self.sidebar)

        center = QFrame(root)
        center.setObjectName("CenterColumn")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        header = QFrame(center)
        header.setObjectName("TopHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 10, 24, 8)
        header_layout.setSpacing(2)
        self.title = QLabel("Library", header)
        self.title.setObjectName("PageTitle")
        self.subtitle = QLabel("Native Qt rebuild foundation", header)
        self.subtitle.setObjectName("Muted")
        header_layout.addWidget(self.title)
        header_layout.addWidget(self.subtitle)
        center_layout.addWidget(header)

        self.stack = QStackedWidget(center)
        center_layout.addWidget(self.stack, 1)
        root_layout.addWidget(center, 1)

        self.inspector = Inspector(root)
        root_layout.addWidget(self.inspector)

        # Shared stores so all pages read/write the same persisted state.
        config_store = ConfigStore.default()
        library_store = LibraryStore.default()
        profile_store = ProfileStore.default()

        self._pages: dict[NavItemId, QWidget] = {
            NavItemId.LIBRARY: LibraryPage(library_store=library_store, profile_store=profile_store, config_store=config_store),
            NavItemId.DISCOVER: DiscoverPage(),
            NavItemId.RUN: RunPage(config_store=config_store, library_store=library_store, profile_store=profile_store),
            NavItemId.PROFILES: ProfilesPage(profile_store=profile_store, library_store=library_store),
            NavItemId.SETTINGS: SettingsPage(),
            NavItemId.DIAGNOSTICS: DiagnosticsPage(),
        }

        for page in self._pages.values():
            self.stack.addWidget(page)
            # Wire page-initiated navigation requests (e.g. Library → Run).
            if hasattr(page, "navigate_requested"):
                page.navigate_requested.connect(self._on_page_navigate)
            if hasattr(page, "inspector_changed"):
                page.inspector_changed.connect(self._on_inspector_changed)

        self.setCentralWidget(root)
        self.navigate(NavItemId.RUN)

    def navigate(self, item_id: NavItemId) -> None:
        page = self._pages[item_id]
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(item_id)
        title = item_id.value.title()
        self.title.setText(title)
        self.subtitle.setText(page.property("subtitle") or "")
        if item_id in {NavItemId.RUN, NavItemId.LIBRARY, NavItemId.PROFILES} and hasattr(page, "_refresh"):
            page._refresh()
        if item_id == NavItemId.LIBRARY:
            discover = self._pages.get(NavItemId.DISCOVER)
            pending = discover.property("pending_library_model_path") if discover is not None else None
            if pending and hasattr(page, "select_model_by_path"):
                page.select_model_by_path(pending)
                discover.setProperty("pending_library_model_path", None)
        elif item_id == NavItemId.RUN and hasattr(page, "_reload_models"):
            page._reload_models()

    def _on_inspector_changed(self, payload: dict) -> None:
        self.inspector.update_details(
            payload.get("title", "Inspector"),
            payload.get("chip_text", "—"),
            payload.get("chip_style", "muted"),
            payload.get("line1", ""),
            payload.get("line2", ""),
            payload.get("command_lines"),
        )

    def _on_page_navigate(self, nav_value: str) -> None:
        """Handle a page's navigate_requested signal."""
        try:
            item_id = NavItemId(nav_value)
        except ValueError:
            return
        self.navigate(item_id)