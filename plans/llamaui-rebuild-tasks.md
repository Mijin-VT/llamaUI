# llamaUI Rebuild Tasks

## Phase 1 — Framework viability gate

- Test Tauri native launch on KDE Wayland + NVIDIA without `GDK_BACKEND=x11`.
- Force-disable the app workaround and confirm Tauri/WebKitGTK crashes with `Error 71`.
- Test PyQt6/PySide6 native Wayland launch with `QApplication.platformName() == \"wayland\"`.
- Verify Qt Wayland platform plugin exists.
- Record the framework decision in `plans/framework-decision.md`.
- Stop Tauri product work and switch implementation to Qt because Tauri requires a WebKitGTK/NVIDIA workaround.

Acceptance: framework decision is evidence-backed. Selected framework is native Wayland/NVIDIA without WebKitGTK workaround compromise.

## Phase 2 — Qt app foundation and persistence model

- Create a new native Qt app skeleton under `qt_app/` without deleting the old Tauri app yet.
- Implement config storage with versioning and migrations.
- Implement local model metadata schema: path, HF repo, HF file, SHA, size, quant, card cache, last used.
- Implement per-model profile schema: model id/path, profile name, settings map, raw args, preset origin, schema version, timestamps.
- Implement service modules for config, profiles, model metadata, library scan, HF API, downloads, and llama-server process control.
- Port useful Rust logic conceptually where it matches the new contracts; do not preserve old frontend-facing assumptions.

Acceptance: Qt app starts natively and backend state can represent global defaults, local models, HF metadata, and multiple profiles per model.

## Phase 3 — Dynamic llama-server introspection

- Add command for selecting and validating `llama-server` binary.
- Run safe introspection on selected binary: `--help`, version command if available, and path metadata.
- Parse supported flags, aliases, defaults, value types, and raw help text.
- Build curated metadata database for detailed option explanations and grouping.
- Merge parsed support with curated metadata; hide unsupported curated options for the selected binary.
- Persist parsed schema keyed by binary path, mtime/hash, and version.
- Add diagnostics showing parsed option count and unknown options.

Acceptance: selected `llama-server` produces a usable option schema with detailed descriptions and exact flag mapping.

## Phase 4 — Frontend shell rewrite

- Replace current tab shell with dense desktop layout: left sidebar, center content, right inspector.
- Implement pages: Library, Discover, Run, Profiles, Settings, Diagnostics.
- Replace global sparse card styling with compact KDE-friendly dark UI system.
- Add reusable components: split panels, collapsible groups, tooltips, badges, command preview, log drawer.
- Remove current user-facing `SetupPage`, `DownloadPage`, `HfModelPage`, `RunPage`, and `StatusPage` flows after replacements exist.

Acceptance: app has a coherent product shell and no scaffold-grade page layout remains.

## Phase 5 — Settings and profile editor rewrite

- Implement Settings page for binary selection, model directory, HF token, global defaults, and diagnostics.
- Implement Run settings editor with main controls always visible.
- Main visible controls: context size, KV cache, CPU threads, GPU layers, batch, ubatch, top-p, top-k, temperature, repeat penalty, host, port, parallel slots.
- Implement Kobold-style collapsible advanced groups: model loading, GPU/offload, context/KV cache, performance, server/API, sampling, multimodal, speculative decoding, debug/logging, raw args.
- Add detailed tooltip/help popovers for every option.
- Add restart-required/runtime-change badges.
- Implement Save Profile, Save As, Duplicate, Reset, Apply Preset.
- Auto-load last/default profile per selected model.

Acceptance: user can configure and save detailed llama.cpp arguments per model without reapplying manually.

## Phase 6 — HuggingFace Discover and downloader rewrite

- Implement robust HF GGUF search using `filter=gguf`, `full=true`, and detail/tree fallback.
- Show repo cards with author, downloads, likes, license, tags, gated/private status.
- Group GGUF files by quantization and split-file set.
- Show exact file sizes when available.
- Detect mmproj/multimodal companion files.
- Compute hardware fit badges for each model/file.
- Implement download queue with progress, cancel, local existence detection, and metadata cache.
- Persist model card and HF metadata after download.

Acceptance: `qwen`, `gemma`, and `llama` searches return useful models, and downloaded files appear in Library with metadata.

## Phase 7 — Library and model detail rewrite

- Implement Library page grouped by HF repo or local folder.
- Show local files with quant, size, fit badge, last used, and profile count.
- Implement model detail page with rendered model card/README, metadata, files, and profiles.
- Add actions: Run, Edit Profile, Create Profile, Reveal File, Open HF, Rescan.
- Cache and display model cards for downloaded models offline when possible.

Acceptance: selecting a downloaded/local model shows its card and saved profiles before running.

## Phase 8 — Runtime, logs, and llama-server API control

- Rewrite process lifecycle to track started, healthy, unhealthy, exited, stopping states.
- Capture stdout/stderr with timestamps and source labels.
- Add log search/filter/copy/clear UI.
- Poll health and capability endpoints for local server.
- Detect runtime model-load API support.
- Implement model switch through API when supported.
- Implement clean restart fallback when API switching is unavailable.
- Show active model, profile, PID, health, endpoint, command, and last error.
- Detect port conflicts before start.

Acceptance: Run page manages local llama-server reliably and transparently shows logs/details.

## Phase 9 — Visual polish and mockup approval pass

- Use mockup direction from `plans/mockup-run-settings.svg` and `plans/mockup-discover-library.svg`.
- Refine typography, spacing, color, and density.
- Add keyboard navigation and accessible labels.
- Ensure tooltip text is readable and not cramped.
- Compare UX against Kobold-style advanced settings and LM Studio-style profile saving.
- Review screenshots with user before final implementation polish.

Acceptance: UI is beautiful, dense, and usable before final verification.

## Phase 10 — End-to-end verification

- Run TypeScript compile.
- Run backend compile/check for selected stack.
- Run production frontend build if applicable.
- Verify native Wayland/NVIDIA launch.
- Verify KDE-native file picker through portal or selected native framework.
- Select `llama-server` binary and parse options.
- Save HF token and validate without global save.
- Search `qwen`, `gemma`, `llama`.
- Download one small GGUF.
- Confirm model card persists and displays.
- Create and save per-model profile.
- Start local llama-server with profile.
- Verify logs, health, command, stop/restart.
- Verify model switch API path if detected; otherwise verify clean restart fallback.

Acceptance: app satisfies the original brief end-to-end on the target KDE Wayland + NVIDIA environment.
