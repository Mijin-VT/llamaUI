# llamaUI Rebuild Plan

## Verdict

The current application is not close to the original brief. It has useful backend fragments, but the frontend and product shape are scaffold-grade and should be replaced. The rebuild should optimize for the actual product: a native desktop UI for `llama-server` that is beautiful, dense, fully configurable, and reliable on KDE Wayland + NVIDIA.

## Non-negotiable requirements

1. Native Wayland + NVIDIA operation with no user launch hacks.
2. User selects the local `llama-server` binary.
3. The app dynamically parses that selected binary's supported options.
4. The UI must provide accurate, detailed, human-readable explanations for options.
5. Main settings stay visible: context, KV cache, CPU threads, GPU layers/offload, batch, top-p, top-k, temperature, repeat penalty, host/port, parallel slots.
6. Advanced settings use Kobold-style collapsible groups.
7. Settings save and auto-restore per model, LM Studio-style.
8. HuggingFace GGUF discovery/downloader must show models, files, sizes, quantization, model cards, and hardware fit.
9. Selected/downloaded models must show model card details and saved profiles.
10. Run page must show process state, active model, command, health, logs, and llama-server API capabilities.
11. Model switching uses llama-server API when detected; otherwise clean restart with the selected model/profile.
12. If Tauri cannot satisfy native Wayland + NVIDIA without compromise, replace Tauri with another native stack such as PyQt6/Qt/QML or another suitable desktop framework.

## Stack decision

### Gate A result: Tauri failed

The Tauri/WebKitGTK path does not satisfy the no-compromise KDE Wayland + NVIDIA requirement on this workstation.

Observed evidence:

- Normal session is KDE Wayland: `XDG_SESSION_TYPE=wayland`, `XDG_CURRENT_DESKTOP=KDE`, `WAYLAND_DISPLAY=wayland-0`.
- Tauri can stay alive only when the app applies the process-local `__NV_DISABLE_EXPLICIT_SYNC` workaround.
- When that workaround is blocked with `__NV_DISABLE_EXPLICIT_SYNC=0`, Tauri/WebKitGTK crashes with `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display`.
- PyQt6 and PySide6 are importable.
- Qt has native Wayland plugin `libqwayland.so`.
- A minimal PyQt6 window ran with `QApplication.platformName() == \"wayland\"` and exited cleanly.

### Selected stack

Switch to a native Qt app. Prefer PySide6 for licensing/distribution, with PyQt6 acceptable for local prototyping because it is installed and smoke-tested. Use Qt Widgets first for dense native desktop UI; reserve QML for later only if needed.

Stop Tauri product implementation. Keep the old Tauri tree temporarily only as reference until the Qt replacement covers the same useful backend behavior.

## Salvage / delete decision

### Keep or salvage

- Rust HF API code, after hardening.
- Rust download manager, after resume/progress/local metadata improvements.
- Rust model profile persistence, after schema redesign.
- Rust llama-server process start/stop/log capture, after lifecycle fixes.
- Hardware probing, after improving NVIDIA/llama.cpp device detection.
- Config store, after adding migration/versioning.

### Replace

- Entire React frontend shell.
- Current `SetupPage`, `DownloadPage`, `HfModelPage`, `RunPage`, `StatusPage` as user-facing screens.
- Current `LLAMA_OPTIONS` static list as source of truth.
- Current sparse layout and card styling.

### Delete or demote

- Tiny hard-coded llama option coverage.
- UI flows that require global Save Settings for local field actions.
- Any fake coverage of llama.cpp arguments.
- Any forced GNOME/GTK dialog path when KDE portal is available.

## Product architecture

### Main UI layout

A dense desktop shell:

- Left sidebar:
  - Library
  - Discover
  - Run
  - Profiles
  - Settings
  - Diagnostics
- Center panel:
  - selected page content
- Right inspector:
  - selected model summary
  - current profile
  - hardware fit
  - active server state

### Library

Purpose: local model inventory.

Features:

- Group downloaded/local GGUF files by known HF repo or folder.
- Show model name, quant, size, local path, last used, profile count.
- Hardware fit badge: GPU likely, partial GPU, CPU only, unlikely.
- Selecting a model opens model detail with model card and profiles.
- Context actions: run, edit profiles, reveal file, delete local metadata, rescan.

### Discover

Purpose: HuggingFace search/downloader.

Features:

- Search GGUF repos using HF API with reliable sibling/file retrieval.
- Model cards in a polished grid/list hybrid.
- Show downloads, likes, license, tags, author, gated/private state.
- Show available GGUF files grouped by quant and split-file family.
- Show exact file sizes where available.
- Show hardware fit before download.
- Download progress, cancel, resume when possible.
- After download, cache metadata and route to model detail.

### Model detail

Purpose: model card + profiles + files.

Features:

- Render model README/model card.
- Show metadata: base model, architecture, context, license, tags, quant files.
- Show downloaded files and missing companion files.
- Show per-model profiles.
- Actions: run selected profile, create profile, edit profile, open HF.

### Run

Purpose: operate local llama-server.

Features:

- Active model/profile selector.
- Main settings always visible:
  - context size
  - KV cache type / cache settings
  - GPU layers/offload
  - CPU threads
  - batch / ubatch
  - parallel slots
  - host / port
  - temperature
  - top-p
  - top-k
  - repeat penalty
- Kobold-style collapsible advanced groups:
  - Model loading
  - GPU / offload
  - Context / KV cache
  - Performance
  - Server / API
  - Sampling defaults
  - Multimodal
  - Speculative decoding if supported
  - Debug / logging
  - Raw extra args
- Every setting has:
  - short label
  - exact flag
  - current value
  - default value
  - detailed tooltip/help text
  - restart/runtime-change badge
  - hardware impact note where relevant
- Effective command line visible and copyable.
- Save profile / Save as preset / Reset / Duplicate.
- Start / Stop / Restart / Load model via API if available.
- Logs/details panel:
  - stdout/stderr
  - API status
  - health
  - server process PID
  - copied command
  - search/filter log lines

### Settings

Purpose: app-level configuration.

Features:

- Select `llama-server` binary.
- Parse and validate selected binary.
- Select model storage directory.
- HF token management with local save/validate.
- Global defaults.
- Portal/dialog diagnostics.
- Wayland/NVIDIA diagnostics.

### Diagnostics

Purpose: make native issues visible.

Features:

- Session type, compositor, GPU vendor, driver hint.
- Portal availability and detected backend.
- Framework/backend currently in use.
- WebView/rendering workaround state if Tauri is retained.
- llama-server version and parsed option count.
- HF API connectivity/token status.

## Dynamic llama-server option strategy

1. User selects `llama-server`.
2. Backend runs safe introspection:
   - `llama-server --help`
   - version command if available
   - optional capability endpoints after server start
3. Parse flags, aliases, defaults, and help text.
4. Merge parsed flags with curated metadata database.
5. Mark unsupported curated options hidden/disabled for that binary.
6. Persist parsed schema keyed by binary path + mtime/hash + version.
7. Surface unknown parsed options in Advanced / Raw group with generic help.

Curated metadata is required because `--help` alone is not enough. The app should ship a maintained metadata file with accurate descriptions for common llama.cpp options and use dynamic parsing for support detection.

## Profile and preset model

Profiles are per model and remembered automatically.

Data model:

- model id / path
- HF repo id, HF filename, SHA when known
- profile id
- profile name
- settings map keyed by option id
- raw extra args
- preset origin if any
- created/updated/last used timestamps
- llama-server schema/version used

Preset types:

- Conservative CPU
- Balanced GPU
- Max VRAM offload
- Long context
- Low memory
- Fast prompt processing
- Custom user presets

Presets are starting points, not hidden magic. User can inspect and save changes per model.

## Runtime control strategy

Local-first only.

- App owns local process by default.
- On start, build argv from selected model/profile.
- Capture stdout/stderr and process lifecycle.
- Poll health and capability endpoints.
- Detect whether runtime model loading API is available.
- If load-model API exists, switch model through API.
- If not, perform clean restart using selected model/profile.
- Keep user informed which path was used.

## HuggingFace strategy

- Use `filter=gguf` and robust detail lookup.
- Do not rely on search results alone for files/sizes.
- Fetch model details/tree when needed.
- Cache model cards and metadata for downloaded models.
- Show gated/private/token-required state clearly.
- Detect split GGUF files and require/download all parts as a set.
- Detect mmproj files for multimodal models.
- Hardware fit estimates use file size + RAM/VRAM + settings assumptions.

## Verification gates

### Framework gate

- Normal launch on KDE Wayland + NVIDIA.
- Native usable rendering.
- KDE portal file picker.
- No `GDK_BACKEND=x11`.

### llama-server gate

- Select binary.
- Parse options.
- Show parsed count and version.
- Start a tiny/local model.
- Capture logs.
- Stop cleanly.

### Options gate

- Main settings visible.
- Advanced groups collapsible.
- Detailed tooltip for every displayed option.
- Saved per-model profile restores after app restart.

### HF gate

- Search `qwen`, `gemma`, `llama` returns models.
- File sizes and quant groups display.
- Hardware fit displays.
- Download one small GGUF.
- Model card persists and displays in Library.

### Runtime gate

- Start selected downloaded model.
- Show health, PID, command, logs.
- Switch model via API if available.
- Clean restart if API unavailable.

## Implementation phases

1. Framework viability gate — completed: Tauri failed, Qt selected.
2. Qt app foundation and persistence model.
3. Dynamic llama-server introspection.
4. Qt frontend shell rewrite.
5. Settings/profile editor rewrite.
6. HF discover/downloader rewrite.
7. Library/model detail/model card rewrite.
8. Runtime/log/API control rewrite.
9. Visual polish and interaction pass.
10. End-to-end verification.

## Current open decisions

1. Whether to implement with PySide6 from the start or prototype with PyQt6 then switch imports.
2. Whether to support only current selected llama-server, or also remember schemas from past binaries.
3. How aggressive hardware recommendations should be when exact model memory requirements are uncertain.
4. Whether presets should be generated from hardware or fixed templates with warnings.
