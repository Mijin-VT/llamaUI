# Router Mode + Model Management — Completion Notes

Date: 2026-06-09

## What was implemented

### Router Mode
- **Mode toggle** in Run page (Single Model / Router)
- **Auto-generated `--models-preset` INI** from library models + saved profiles
  - Per-model settings (ctx-size, n-gpu-layers, batch-size, temperature, etc.)
  - Auto-attached mmproj from library scan
  - Companion GGUFs (mmproj, text-encoder) excluded from preset
  - `extra_args` meta-option excluded from INI
- **No `--models-dir`** — preset alone defines the model catalogue
- **Max loaded models** spinner with `--models-max` flag
- **Loaded models panel** with unload buttons (polls `GET /models`)
- **Server re-attach** on app restart via `try_attach(host, port)`

### Bug Fixes
- Bus error crash: replaced `moveToThread`+`QueuedConnection` with `QThread` subclasses
- Search crash: same fix for `_SearchWorker`/`_CardWorker`
- STOP button: fixed indentation bug, async stop
- Settings propagation: config host/port now authoritative
- Library buttons: added missing `os`/`webbrowser` imports
- Library floating widget: added missing `layout.addWidget` for card_text
- QLayout warning: removed duplicate `layout.addLayout` in settings
- Default host: `0.0.0.0` in both `AppConfig` and catalog option
- Missing imports in library.py, settings.py, runtime.py (from code review)
- `AppConfig.to_json()` now serializes `global_settings` and `selected_profile_id`

### UI Fixes
- Constrained 27+ widgets across all pages (size policies, word wrap, elide)
- Fixed advanced card height on mode switch
- Text wrapping on command preview, logs, FieldTile, MonoLog
- Profile combo elide and mode combo sizing
- Library tags row wrapped in proper QWidget container
- ElidedLabel for router model names
- 2-pane layout (sidebar + center, no right inspector)

### Cross-Platform
- `pyproject.toml` with pip-installable `llamaui` entry point
- `llamaui.sh` (Unix) / `llamaui.bat` (Windows) launchers
- `install.sh` (Linux desktop + macOS .app) / `install.bat` (Windows)
- App icon at 9 sizes with window icon loading

## Files changed

Key files (55 total):
- `qt_app/app/pages/run.py` — mode toggle, router panel, preset wiring
- `qt_app/app/pages/library.py` — import fixes, floating widget, button fixes
- `qt_app/app/pages/settings.py` — SettingValueMap import, shared models dir widget
- `qt_app/app/services/runtime.py` — `generate_models_preset`, `try_attach`, `_find_pid_for_port`
- `qt_app/app/services/runtime_api.py` — `list_loaded_models`, `unload_model`, `load_model`
- `qt_app/llama_data/models.py` — host default, `to_json` serialization
- `qt_app/llama_data/llama_options.py` — `models_max` catalog entry, host default
- `qt_app/main.py` — sys.path fix for entry point
- `qt_app/app/application.py` — window icon, desktop file name

## Smoke tests passing
- smoke_section0, smoke_section6, smoke_section10, smoke_section11, smoke_section13

## Pre-existing test failures (unrelated)
- smoke_section1: references deleted `_DownloadWorker`
- smoke_runtime: profile ctx_size assertion (defense-in-depth correctly skips catalog defaults)
