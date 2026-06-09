# Repository Atlas: llamUI

## Project Responsibility

llamUI is a desktop launcher and manager for `llama-server`. The repository currently contains two UI stacks over the same domain: a React + Tauri implementation (`src/`, `src-tauri/`) and a native PySide6/Qt implementation (`qt_app/`). Both surfaces help users configure local model storage, discover/download GGUF models from Hugging Face, tune runtime settings, launch/monitor `llama-server`, and collect host diagnostics.

## System Entry Points

- `package.json`: Vite/Tauri frontend manifest. Scripts: `dev`, `build`, `preview`, `tauri`; dependencies include React 18, Tauri v2 APIs/plugins, and markdown rendering.
- `vite.config.ts`: React plugin and Tauri dev server settings (`1420`, strict port, optional `TAURI_DEV_HOST` HMR). Defines `@shared` and `@pages` aliases and ignores `src-tauri` in Vite file watching.
- `tsconfig.json`: Strict TypeScript configuration for `src/` with bundler module resolution and path aliases matching Vite.
- `src/main.tsx`: React WebView entry; renders `<App />` into `#root`.
- `src-tauri/src/main.rs`: Tauri backend entry; applies Linux NVIDIA/Wayland workaround, manages shared state, and registers IPC commands.
- `qt_app/main.py`: Native Qt script entry; creates the themed `QApplication`, constructs `MainWindow`, and enters the Qt event loop.
- `qt_app/__main__.py`: Package-mode entry for `python -m qt_app`.

## Directory Map (Aggregated)

| Directory | Responsibility Summary | Detailed Map |
|-----------|------------------------|--------------|
| `src/` | React + TypeScript Tauri WebView layer; owns SPA shell, lifted navigation/shared state, page composition, and calls into the typed Tauri IPC gateway. | [View Map](src/codemap.md) |
| `src/pages/` | Top-level React page components for setup, HF search/download, model details, run configuration, server status, and diagnostics. | [View Map](src/pages/codemap.md) |
| `src/shared/` | Frontend shared kernel: Rust-mirrored TypeScript types, Tauri command/event wrappers, and the declarative `llama-server` option catalog. | [View Map](src/shared/codemap.md) |
| `src-tauri/` | Tauri v2 Rust backend crate/configuration; exposes host-system operations to React through command-per-operation IPC. | [View Map](src-tauri/codemap.md) |
| `src-tauri/src/` | Rust domain modules for config persistence, Hugging Face API access, downloads, model stores/profiles, hardware scanning, recommendations, server process lifecycle, and diagnostics. | [View Map](src-tauri/src/codemap.md) |
| `qt_app/` | Native PySide6 application package; script/package entry points, Qt application bootstrap, shared stores, and cleanup utility. | [View Map](qt_app/codemap.md) |
| `qt_app/app/` | Qt shell composition layer: `QApplication` factory, `MainWindow`, navigation/sidebar wiring, persisted splitter state, and global dark theme. | [View Map](qt_app/app/codemap.md) |
| `qt_app/app/pages/` | Full-page Qt widgets for library, discovery/downloads, settings, run lifecycle/options, diagnostics, and placeholders. | [View Map](qt_app/app/pages/codemap.md) |
| `qt_app/app/services/` | UI-independent service layer for subprocess runtime control, HF/network I/O, downloads, library scanning, binary validation, option-schema parsing, dialogs, and diagnostics. | [View Map](qt_app/app/services/codemap.md) |
| `qt_app/app/widgets/` | Reusable theme-aware Qt widgets and shell chrome: semantic buttons, cards/chips/log rows, collapsible groups, flow layout, sidebar, inspector, and slider/spin composites. | [View Map](qt_app/app/widgets/codemap.md) |
| `qt_app/llama_data/` | Qt app data/persistence layer: platform data paths, defensive domain models, versioned JSON stores/migrations, file locking, and schema-driven CLI option values. | [View Map](qt_app/llama_data/codemap.md) |

## Cross-Cutting Flow

1. **React/Tauri path**: `src/main.tsx` renders `App.tsx`; pages call `src/shared/tauriApi.ts`; Tauri commands in `src-tauri/src/main.rs` dispatch into Rust domain modules; long-running work emits frontend events (`download-progress`, `server-log`, `server-started`).
2. **Qt path**: `qt_app/main.py` creates `MainWindow`; pages interact with `qt_app.llama_data` stores and `qt_app.app.services`; service objects perform network/filesystem/subprocess work and notify pages via Qt signals/callbacks.
3. **Runtime settings**: both stacks treat `llama-server` flags as schema/data rather than ad-hoc UI code (`src/shared/llamaOptions.ts`, `qt_app/llama_data/llama_options.py`).
4. **Persistence**: Tauri persists JSON in app data through Rust state modules; Qt persists versioned JSON envelopes through `ConfigStore`, `LibraryStore`, and `ProfileStore`.
