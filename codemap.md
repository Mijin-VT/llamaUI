# Repository Atlas: llamaUI

## Project Responsibility

llamaUI is a native desktop launcher and manager for `llama-server`, built with PySide6/Qt. The application helps users configure local model storage, discover/download GGUF models from Hugging Face, tune runtime settings, launch/monitor `llama-server`, and collect host diagnostics.

## System Entry Points

- `qt_app/main.py`: Native Qt script entry; creates the themed `QApplication`, constructs `MainWindow`, and enters the Qt event loop.
- `qt_app/__main__.py`: Package-mode entry for `python -m qt_app`.

## Directory Map (Aggregated)

| Directory | Responsibility Summary | Detailed Map |
|-----------|------------------------|--------------|
| `qt_app/` | Native PySide6 application package; script/package entry points, Qt application bootstrap, shared stores, and cleanup utility. | [View Map](qt_app/codemap.md) |
| `qt_app/app/` | Qt shell composition layer: `QApplication` factory, `MainWindow`, navigation/sidebar wiring, persisted splitter state, and global dark theme. | [View Map](qt_app/app/codemap.md) |
| `qt_app/app/pages/` | Full-page Qt widgets for library, discovery/downloads, settings, run lifecycle/options, real-time metrics dashboard, diagnostics, and placeholders. | [View Map](qt_app/app/pages/codemap.md) |
| `qt_app/app/services/` | UI-independent service layer for subprocess runtime control, HF/network I/O, downloads, library scanning, binary validation, option-schema parsing, dialogs, and diagnostics. | [View Map](qt_app/app/services/codemap.md) |
| `qt_app/app/widgets/` | Reusable theme-aware Qt widgets and shell chrome: semantic buttons, cards/chips/log rows, collapsible groups, flow layout, sidebar, inspector, and slider/spin composites. | [View Map](qt_app/app/widgets/codemap.md) |
| `qt_app/icons/` | Bundled SVG nav icons used by the collapsible sidebar. |
| `qt_app/llama_data/` | Qt app data/persistence layer: platform data paths, defensive domain models, versioned JSON stores/migrations, file locking, and schema-driven CLI option values. | [View Map](qt_app/llama_data/codemap.md) |

## Cross-Cutting Flow

1. **Bootstrap** — Entry point (`qt_app/main.py` or `__main__.py`) calls `create_app()` to get a themed `QApplication`, then instantiates `MainWindow` and calls `show()`.
2. **Runtime settings** — `llama-server` flags are treated as schema/data rather than ad-hoc UI code (`qt_app/llama_data/llama_options.py`).
3. **Persistence** — Qt persists versioned JSON envelopes through `ConfigStore`, `LibraryStore`, and `ProfileStore`.
