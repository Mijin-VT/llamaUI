# llamUI

A native desktop UI for [llama.cpp](https://github.com/ggerganov/llama.cpp)'s `llama-server`. Built with PySide6 / Qt Widgets, targeting Linux (KDE Wayland + NVIDIA tested). It is **not** a web app wrapped in Electron — it is a real Qt application that talks directly to the llama-server binary.

This project started as a Tauri app, but WebKitGTK crashes on Wayland with NVIDIA explicit-sync unless you apply workaround env vars. That was unacceptable for a daily-driver tool, so the whole thing was rewritten in PySide6. The old Tauri source is still in `src/` and `src-tauri/` for reference, but it is no longer maintained.

## What it actually does

### Library
Scan a directory of GGUF files. The scanner distinguishes **primary runnable models** from **companion files** (mmproj, text-encoder, vision-encoder, embedding GGUFs) and links them together. Each model gets a card showing its quant, size, and hardware-fit estimate based on your detected RAM / VRAM.

### Discover
Search HuggingFace for GGUF models. Results show quant variants, split-set
detection (multi-part GGUFs), and a hardware-fit score. You can download
directly — the download manager runs up to 3 files concurrently and each
file gets its own progress row with a cancel button. Interrupted
downloads pick up where they left off thanks to HTTP Range resume. Model
cards are cached locally so you can read them offline later.

### Run
This is the control center.

- **Pick a model** from your library.
- **Edit its launch arguments** through a form UI that mirrors `llama-server --help`. The app can either parse the actual `--help` output from your binary (so it stays current with whatever llama.cpp version you have) or fall back to a static catalog.
- **Save profiles** per-model directly in the Run page. Each profile stores its own set of arguments. Create, duplicate, reset, or apply presets like "Conservative CPU", "Balanced GPU", or "Low Memory" with one click.
- **Start / stop / restart** the server. The process is launched in its own POSIX session group (`start_new_session=True`) so when you hit Stop, `os.killpg` terminates the entire process tree — no orphaned worker threads left behind.
- **Live logs** with auto-tail scrolling. Filter by stdout/stderr or search the buffer.
- **Command preview** shows the exact argv that will be passed to llama-server before you start it.
- **API health** polling. If the server is up, you can switch models via the `/model` endpoint without a full restart (falls back to restart if the endpoint is missing or the model is incompatible).

### Settings
- Point to your `llama-server` binary.
- Set the models download directory.
- Configure your HuggingFace token (saved to config, or read from `HF_TOKEN` env var).
- Global defaults for host, port, and context size.

### Diagnostics
A quick health check page. Probes:
- Qt framework / platform plugin (confirms native Wayland if available)
- llama-server binary presence and version
- HuggingFace API reachability
- GPU detection (NVIDIA via `nvidia-smi`)

## How it works

### Architecture
- **Frontend**: PySide6 Qt Widgets. No QML. The shell is a `QMainWindow` with a sidebar, a `QStackedWidget` for pages, and a collapsible inspector panel. Splitter sizes persist via `QSettings`.
- **Data layer**: Plain Python dataclasses + JSON files. `ConfigStore`, `LibraryStore`, and `ProfileStore` each own a versioned JSON envelope with migration hooks. Stores live in `~/.local/share/llamaUI/`.
- **Background tasks**: `QThread` workers for search, downloads, and log reading. They dispatch updates back to the UI via Qt signals.
- **Option schema**: On first run (or when the binary changes), the app runs `llama-server --help`, parses the output with a regex-based parser, and caches the resulting schema to disk. This means the UI stays accurate even if you upgrade llama.cpp and new flags appear.
- **Argument building**: `build_argv` assembles the final command line from (1) global settings, (2) profile settings, (3) raw extra args. It filters out natural defaults (`0`, `""`, `[]`) so the command line stays clean.

### Key design decisions
- **No mock data in production paths**. Empty states are honest — if you have no models, the Library page says so.
- **Slider + spinbox pairs**: Every numeric control is a composite widget where the slider and the spinbox share the same value model. Dragging updates the number; typing updates the slider.
- **Process group termination**: We start the server with `start_new_session=True` so `os.killpg(pgid, signal.SIGKILL)` reliably cleans up auxiliary workers.
- **Companion file filtering**: The library scanner knows that `mmproj-*.gguf`, `*-encoder-*.gguf`, and `*-embedding-*.gguf` are not standalone models. It attaches them to the primary model in the same directory.

## Requirements

- Python 3.11+
- A working `llama-server` binary (build it from [llama.cpp](https://github.com/ggerganov/llama.cpp) or grab a release)
- Linux with a display server (X11 or Wayland). Developed and tested on KDE Plasma Wayland + NVIDIA RTX 4090.
- `nvidia-smi` in your path if you want GPU detection.

## Installation

Clone the repo and install dependencies:

```bash
git clone https://github.com/NickPittas/llamUI.git
cd llamUI

# Create a venv (recommended)
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install PySide6 httpx
```

That's it. No build step, no npm, no cargo.

## Running

```bash
# Package mode
python -m qt_app

# Or directly
python qt_app/main.py
```

On first launch, go to **Settings**, point it at your `llama-server` binary and your models directory, then hit **Scan Library**.

## Project layout

```
llamUI/
├── qt_app/                 # The actual application
│   ├── app/
│   │   ├── pages/          # Library, Discover, Run, Settings, Diagnostics
│   │   ├── services/       # HF search, download, runtime, scanner, parser
│   │   ├── widgets/        # Cards, buttons, slider+spinbox, sidebar, inspector
│   │   ├── main_window.py  # Shell layout
│   │   ├── application.py  # QApplication bootstrap
│   │   └── theme.py        # Dark palette + QSS stylesheet
│   ├── llama_data/         # Models, stores, option catalog, migrations
│   ├── tests/              # Smoke tests (no pytest needed)
│   └── main.py             # Entry point
├── plans/                  # Architecture decision records
├── src/                    # Old Tauri frontend (archived)
└── src-tauri/              # Old Tauri backend (archived)
```

## Smoke tests

There is no heavy test framework. Just run the smoke files directly:

```bash
python qt_app/tests/smoke_services.py      # Data stores, scanner, parser
python qt_app/tests/smoke_runtime_api.py   # Server API client
python qt_app/tests/smoke_section15.py     # UI layout sanity (no horizontal overflow)
```

These exercises real code paths against temporary directories. They do not mock anything.

## Why not Tauri?

See `plans/framework-decision.md`. In short: WebKitGTK on Wayland + NVIDIA crashes with `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display.` unless you disable explicit sync, which is not something a user-facing app should require. Qt's native Wayland plugin handles the same hardware without workarounds.

## Known limitations

- The download manager is single-file-at-a-time per queue entry. Parallel downloads would need a second queue layer.
- Model switching via API only works if your `llama-server` build supports the `/model` endpoint (relatively recent llama.cpp).
- No Windows or macOS testing has been done. The paths and process logic assume POSIX.

## License

The project is unlicensed for now. If you use it, you are on your own.
