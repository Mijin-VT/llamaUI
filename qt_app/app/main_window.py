from __future__ import annotations
import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from llama_data import ConfigStore, LibraryStore, ProfileStore

from .pages.base import PagePolicy
from .pages.diagnostics import DiagnosticsPage
from .pages.discover import DiscoverPage
from .pages.library import LibraryPage
from .pages.run import RunPage
from .pages.settings import SettingsPage
from . import theme
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
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar(root)
        self.sidebar.navigated.connect(self.navigate)

        center = QFrame(root)
        center.setObjectName("CenterColumn")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
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

        self.inspector = Inspector(root)

        # --- QSplitter layout -------------------------------------------------
        self._splitter = QSplitter(Qt.Orientation.Horizontal, root)
        self._splitter.setContentsMargins(0, 0, 0, 0)
        self._splitter.setHandleWidth(1)
        self._splitter.addWidget(self.sidebar)
        self._splitter.addWidget(center)
        self._splitter.addWidget(self.inspector)
        root_layout.addWidget(self._splitter, 1)

        # Default sizes: sidebar | center | inspector
        self._default_sizes = [
            theme.SIDEBAR_DEFAULT_WIDTH,
            760,
            theme.INSPECTOR_DEFAULT_WIDTH,
        ]
        self._splitter.setSizes(self._default_sizes)

        # Stretch factors: sidebar=0, center=1 (stretches), inspector=0
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        # Persist splitter sizes via QSettings
        self._settings = QSettings(theme.SPLITTER_KEY, QSettings.Format.IniFormat)
        self._splitter.splitterMoved.connect(self._save_splitter_sizes)
        self._restore_splitter_sizes()

        # Shared stores so all pages read/write the same persisted state.
        config_store = ConfigStore.default()
        library_store = LibraryStore.default()
        # One-time library cleanup (v1→v2 migration) runs automatically
        # inside LibraryStore.load(): companion GGUF entries from
        # pre-Phase-11 scans are stripped and the file is saved at the
        # current schema version. No inline wipe here.
        profile_store = ProfileStore.default()

        self._pages: dict[NavItemId, QWidget] = {
            NavItemId.LIBRARY: LibraryPage(library_store=library_store, profile_store=profile_store, config_store=config_store),
            NavItemId.DISCOVER: DiscoverPage(),
            NavItemId.RUN: RunPage(config_store=config_store, library_store=library_store, profile_store=profile_store),
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

    # -- splitter persistence --------------------------------------------------

    def _save_splitter_sizes(self) -> None:
        self._settings.setValue("sizes", self._splitter.sizes())

    def _restore_splitter_sizes(self) -> None:
        saved = self._settings.value("sizes")
        if saved is not None:
            try:
                sizes = [int(s) for s in saved]
                if len(sizes) == 3:
                    self._splitter.setSizes(sizes)
            except (ValueError, TypeError):
                pass

    # -- inspector visibility --------------------------------------------------

    def set_inspector_visible(self, visible: bool) -> None:
        """Toggle the inspector panel and adjust splitter sizes accordingly."""
        if visible:
            self.inspector.show()
            sizes = self._splitter.sizes()
            # If inspector is zero-width, restore it to default
            if sizes[2] < theme.INSPECTOR_MIN_WIDTH:
                sizes[2] = theme.INSPECTOR_DEFAULT_WIDTH
                self._splitter.setSizes(sizes)
        else:
            self.inspector.hide()
            sizes = self._splitter.sizes()
            sizes[2] = 0
            self._splitter.setSizes(sizes)

    def _set_inspector_collapsed(self, collapsed: bool) -> None:
        """Collapse/expand the inspector content while keeping it in the splitter."""
        if collapsed:
            sizes = self._splitter.sizes()
            sizes[2] = 0
            self._splitter.setSizes(sizes)
            self.inspector._do_collapse()
        else:
            sizes = self._splitter.sizes()
            sizes[2] = theme.INSPECTOR_DEFAULT_WIDTH
            self._splitter.setSizes(sizes)
            self.inspector._on_expand()

    # -- navigation ------------------------------------------------------------

    def navigate(self, item_id: NavItemId) -> None:
        page = self._pages[item_id]
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(item_id)
        title = item_id.value.title()
        self.title.setText(title)
        self.subtitle.setText(page.property("subtitle") or "")

        # PagePolicy drives inspector visibility
        policy = getattr(page, "policy", PagePolicy.STANDARD)
        if policy == PagePolicy.FULL_WIDTH:
            self.set_inspector_visible(False)
        elif policy == PagePolicy.INSPECTOR_OPTIONAL:
            self.set_inspector_visible(True)
            self._set_inspector_collapsed(True)
        else:
            self.set_inspector_visible(True)
            self._set_inspector_collapsed(False)

        if item_id in {NavItemId.RUN, NavItemId.LIBRARY} and hasattr(page, "_refresh"):
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
