# llamUI

A native desktop UI for [llama.cpp](https://github.com/ggerganov/llama.cpp)'s `llama-server`. Built with PySide6 / Qt Widgets, targeting Linux (KDE Wayland + NVIDIA tested). It is **not** a web app wrapped in Electron — it is a real Qt application that talks directly to the llama-server binary.

This project started as a Tauri app, but WebKitGTK crashes on Wayland with NVIDIA explicit-sync unless you apply workaround env vars. That was unacceptable for a daily-driver tool, so the whole thing was rewritten in PySide6. The old Tauri source is still in `src/` and `src-tauri/` for reference, but it is no longer maintained.

## What it does

### Library
Scan a directory of GGUF files. The scanner distinguishes **primary runnable models** from **companion files** (mmproj, text-encoder, vision-encoder, embedding GGUFs) and links them together. Each model gets a card showing its quant, size, and hardware-fit estimate based on your detected RAM / VRAM. Browse the model's HuggingFace page or reveal the file in your file manager.

### Discover
Search HuggingFace for GGUF models. Results show quant variants, split-set detection (multi-part GGUFs), and a hardware-fit score. Download directly — the download manager runs up to 3 files concurrently, each with its own progress row and cancel button. Interrupted downloads resume via HTTP Range. Model cards are cached locally for offline reading.

### Run
The control center. Two modes:

**Single Model** — Pick a model, configure launch arguments through a form UI that mirrors `llama-server --help` (auto-parsed from your binary), save per-model profiles with presets like "Conservative CPU" or "Balanced GPU", start/stop/restart with live logs and command preview.

**Router Mode** — Serve all models from your library via llama-server's native router. The app auto-generates a `--models-preset` INI from your saved profiles, so each model gets its own context size, GPU layers, mmproj, and other settings. Companion GGUFs are automatically excluded. A loaded models panel shows what's in VRAM with unload buttons. Set max loaded models to control VRAM usage with LRU eviction.

Additional features:
- **Server re-attach**: If llama-server is already running when you open the app, it attaches to the existing process for stop/restart control — no orphaned servers.
- **API health polling**: Live status, token throughput, and model switching.
- **Command preview**: See the exact argv before you start.
- **Live logs**: Auto-tail scrolling with stdout/stderr filtering and search.

### Settings
- Point to your `llama-server` binary.
- Set the models download directory.
- Configure bind host and port (defaults to `0.0.0.0:8080` for LAN access).
- Toggle router mode with models directory.
- HuggingFace token (saved to config, or read from `HF_TOKEN` env var).
- Global defaults for all llama-server options.

### Diagnostics
Quick health check: Qt platform plugin, llama-server binary presence/version, HuggingFace API reachability, GPU detection (NVIDIA via `nvidia-smi`).

## Architecture

- **Frontend**: PySide6 Qt Widgets. No QML. Two-pane splitter layout: sidebar navigation + page stack. Runtime status lives in the sidebar.
- **Data layer**: Plain Python dataclasses + JSON files. `ConfigStore`, `LibraryStore`, and `ProfileStore` each own a versioned JSON envelope with migration hooks. Stores live in `~/.local/share/llamaUI/`.
- **Background tasks**: `QThread` subclasses for search, downloads, and server management. They dispatch updates back to the UI via Qt signals.
- **Option schema**: On first run (or when the binary changes), the app runs `llama-server --help`, parses the output, and caches the schema. The UI stays accurate even if you upgrade llama.cpp and new flags appear.
- **Router preset**: `generate_models_preset()` writes an INI file listing every runnable model with per-model settings from saved profiles. `mmproj` is auto-attached from the library scan. Companion files are excluded. No `--models-dir` needed — the preset alone defines the model catalogue.

### Key design decisions
- **No mock data in production paths**. Empty states are honest.
- **QThread subclasses over moveToThread**: `moveToThread` + `QueuedConnection` with Python callables mis-dispatches to the main thread in PySide6, causing bus errors. QThread subclasses avoid this.
- **Process group termination**: Server starts with `start_new_session=True` so `os.killpg` cleans up the entire process tree on Stop.
- **Companion file filtering**: The scanner knows `mmproj-*.gguf`, `*-encoder-*.gguf`, and `*-embedding-*.gguf` are not standalone models. It attaches them to the primary model.
- **Config host/port authoritative**: Profile host/port never overrides saved Settings values.

## Requirements

- Python 3.10+
- PySide6 >= 6.6
- Pillow >= 10.0
- A working `llama-server` binary ([build from llama.cpp](https://github.com/ggerganov/llama.cpp) or grab a release)
- Linux with X11 or Wayland (developed on KDE Plasma Wayland + NVIDIA RTX 5090)
- `nvidia-smi` in PATH for GPU detection

## Installation

### Quick start (any OS)

```bash
git clone https://github.com/NickPittas/llamUI.git
cd llamUI

# Option 1: pip install (creates 'llamaui' command)
pip install -e .
llamaui

# Option 2: run directly
python -m qt_app

# Option 3: use the launcher script
./llamaui.sh          # Linux/macOS
llamaui.bat           # Windows
```

### System integration (Linux/macOS)

```bash
./install.sh
```

This installs:
- The `llamaui` command via pip
- XDG desktop entry + icons (Linux — shows in app launcher)
- .app bundle stub (macOS — shows in ~/Applications)

On first launch, go to **Settings**, point it at your `llama-server` binary and your models directory, then hit **Scan Library**.

## Project layout

```
llamUI/
├── qt_app/                 # The application
│   ├── app/
│   │   ├── pages/          # Library, Discover, Run, Settings, Diagnostics
│   │   ├── services/       # HF search, download, runtime, scanner, parser
│   │   ├── widgets/        # Cards, buttons, slider+spinbox, sidebar
│   │   ├── main_window.py  # Two-pane shell layout
│   │   ├── application.py  # QApplication bootstrap + window icon
│   │   └── theme.py        # Dark palette + QSS stylesheet
│   ├── llama_data/         # Models, stores, option catalog, migrations
│   ├── icons/              # App icon at 9 sizes (16px–512px)
│   ├── tests/              # Smoke tests (no pytest needed)
│   └── main.py             # Entry point (handles all invocation styles)
├── plans/                  # Architecture decision records
├── pyproject.toml          # pip-installable package definition
├── install.sh              # Cross-platform installer (Linux/macOS)
├── install.bat             # Windows installer
├── llamaui.sh              # Unix launcher
├── llamaui.bat             # Windows launcher
├── src/                    # Old Tauri frontend (archived)
└── src-tauri/              # Old Tauri backend (archived)
```

## Smoke tests

No heavy test framework — just run the smoke files directly:

```bash
python -m qt_app.tests.smoke_section0         # Shell layout sanity
python -m qt_app.tests.smoke_services         # Data stores, scanner, parser
python -m qt_app.tests.smoke_runtime          # build_argv, preset generation
python -m qt_app.tests.smoke_runtime_api      # Server API client
python -m qt_app.tests.smoke_download_manager # Download concurrency
```

These exercise real code paths against temporary directories. No mocks.

## Router mode

llamUI's router mode uses llama-server's native `--models-preset` feature to serve multiple models simultaneously:

1. **Auto-generates a preset INI** from your library and saved profiles
2. **Each model gets its own settings** — context size, GPU layers, batch size, temperature, mmproj
3. **Companion files filtered** — only actual chat models appear to clients
4. **mmproj auto-attached** — multimodal models work without manual configuration
5. **Max loaded models** — control VRAM usage with LRU eviction
6. **Loaded models panel** — see what's in VRAM, unload on demand

Connect from any OpenAI-compatible client (Odysseus, Open WebUI, etc.) to `http://<host>:<port>`.

## Why not Tauri?

See `plans/framework-decision.md`. In short: WebKitGTK on Wayland + NVIDIA crashes with `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display.` unless you disable explicit sync, which is not something a user-facing app should require. Qt's native Wayland plugin handles the same hardware without workarounds.

## Known limitations

- Router mode is built on llama-server's experimental router feature. Check your llama.cpp version supports `--models-preset`.
- The download manager is single-file-at-a-time per queue entry.
- Windows and macOS are supported via the launcher scripts but have not been extensively tested.

## License

The project is unlicensed for now. If you use it, you are on your own.
