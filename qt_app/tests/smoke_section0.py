"""Smoke test: Section 0 — responsive shell, QSplitter, PagePolicy."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.application import create_app  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.pages.base import PagePolicy  # noqa: E402
from app.widgets.sidebar import NavItemId  # noqa: E402
from app import theme  # noqa: E402

if not app.styleSheet():
    create_app()

# -- construct the window ----------------------------------------------------
win = MainWindow()
win.show()

splitter = win._splitter


def _inspector_width() -> int:
    return splitter.sizes()[2]


def _sidebar_width() -> int:
    return splitter.sizes()[0]


# -- Test 1: default navigation lands on RUN (STANDARD policy) ---------------
assert _inspector_width() >= theme.INSPECTOR_MIN_WIDTH, (
    f"RUN page (STANDARD) should show inspector, got width={_inspector_width()}"
)
print(f"PASS: RUN page inspector width = {_inspector_width()}")

# -- Test 2: navigate to Library (STANDARD) ---------------------------------
win.navigate(NavItemId.LIBRARY)
assert _inspector_width() >= theme.INSPECTOR_MIN_WIDTH, (
    f"LIBRARY page (STANDARD) should show inspector, got width={_inspector_width()}"
)
print(f"PASS: Library page inspector width = {_inspector_width()}")

# -- Test 3: navigate to Discover (STANDARD) --------------------------------
win.navigate(NavItemId.DISCOVER)
assert _inspector_width() >= theme.INSPECTOR_MIN_WIDTH, (
    f"DISCOVER page (STANDARD) should show inspector, got width={_inspector_width()}"
)
win.navigate(NavItemId.SETTINGS)
assert _inspector_width() == 0, (
    f"SETTINGS page (INSPECTOR_OPTIONAL) should collapse inspector, got width={_inspector_width()}"
)
print(f"PASS: Settings page inspector collapsed, width = {_inspector_width()}")
# -- Test 5: navigate to Diagnostics (FULL_WIDTH → hidden) ------------------
win.navigate(NavItemId.DIAGNOSTICS)
assert _inspector_width() == 0, (
    f"DIAGNOSTICS page (FULL_WIDTH) should have zero inspector width, got {_inspector_width()}"
)
print("PASS: Diagnostics page inspector hidden")


# -- Test 6: navigate back to RUN → inspector restored ----------------------
win.navigate(NavItemId.RUN)
assert win.inspector.isVisible(), (
    "Navigating back to RUN should restore inspector visibility"
)
assert _inspector_width() >= theme.INSPECTOR_MIN_WIDTH, (
    f"RUN page should restore inspector, got width={_inspector_width()}"
)
print(f"PASS: RUN page restored inspector, width = {_inspector_width()}")

# -- Test 7: set_inspector_visible toggles correctly ------------------------
win.set_inspector_visible(False)
assert not win.inspector.isVisible(), "set_inspector_visible(False) should hide inspector"
assert _inspector_width() == 0, f"Hidden inspector should be 0 width, got {_inspector_width()}"
print("PASS: set_inspector_visible(False)")

win.set_inspector_visible(True)
assert win.inspector.isVisible(), "set_inspector_visible(True) should show inspector"
assert _inspector_width() >= theme.INSPECTOR_MIN_WIDTH, (
    f"Restored inspector should be >= min, got {_inspector_width()}"
)
print(f"PASS: set_inspector_visible(True), width = {_inspector_width()}")

# -- Test 8: sidebar uses minimum width, not fixed --------------------------
sw = win.sidebar
assert sw.minimumWidth() == theme.SIDEBAR_MIN_WIDTH, (
    f"Sidebar minimumWidth should be {theme.SIDEBAR_MIN_WIDTH}, got {sw.minimumWidth()}"
)
print(f"PASS: Sidebar minimumWidth = {sw.minimumWidth()}")

# -- Test 9: inspector uses minimum width, not fixed ------------------------
iw = win.inspector
assert iw.minimumWidth() == theme.INSPECTOR_MIN_WIDTH, (
    f"Inspector minimumWidth should be {theme.INSPECTOR_MIN_WIDTH}, got {iw.minimumWidth()}"
)
print(f"PASS: Inspector minimumWidth = {iw.minimumWidth()}")


from app.pages.library import LibraryPage  # noqa: E402
from app.pages.run import RunPage  # noqa: E402
from app.pages.settings import SettingsPage  # noqa: E402
from app.pages.diagnostics import DiagnosticsPage  # noqa: E402

assert LibraryPage.policy == PagePolicy.STANDARD
assert RunPage.policy == PagePolicy.STANDARD
assert SettingsPage.policy == PagePolicy.INSPECTOR_OPTIONAL
assert DiagnosticsPage.policy == PagePolicy.FULL_WIDTH
print("PASS: All page policies match expected values")

# -- Test 10: QSplitter structure -------------------------------------------
assert splitter.count() == 3, f"Splitter should have 3 children, got {splitter.count()}"
assert splitter.widget(0) is win.sidebar
assert splitter.widget(1).objectName() == "CenterColumn"
assert splitter.widget(2) is win.inspector
print("PASS: Splitter children are [sidebar, center, inspector]")

print("\n=== All Section 0 smoke tests passed ===")
