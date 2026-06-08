"""Application entry point.

Supports both invocation styles:

- ``python qt_app/main.py`` — script mode (the package parent is added
  to ``sys.path`` automatically, so absolute ``qt_app.app`` imports work).
- ``python -m qt_app`` — package mode (uses relative imports).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional


def _ensure_package_importable() -> None:
    """Make ``import qt_app`` work when run as a bare script.

    When Python runs ``qt_app/main.py`` directly, only ``qt_app/`` ends up
    on ``sys.path``. Adding the parent directory lets absolute imports
    resolve the ``qt_app`` package regardless of how the script is launched.
    """
    pkg_parent = Path(__file__).resolve().parent.parent
    pkg_parent_str = str(pkg_parent)
    if pkg_parent_str not in sys.path:
        sys.path.insert(0, pkg_parent_str)


_ensure_package_importable()

from qt_app.app import MainWindow, create_app  # noqa: E402  (after sys.path fix)


def main(argv: Optional[List[str]] = None) -> int:
    """Configure the QApplication, show the shell, and run the event loop."""
    app = create_app(argv if argv is not None else sys.argv)

    window = MainWindow()
    window.show()

    # exec() returns the exit code set by the last window to close.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
