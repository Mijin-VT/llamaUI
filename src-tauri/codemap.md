# `src-tauri/` Codemap — Tauri v2 Rust Backend

## Responsibility

This crate is the native backend for LlamUI. It bridges the React/TypeScript frontend to the host system via Tauri v2 IPC, and encapsulates all non-UI concerns:

- **Configuration persistence** (`config_store`) — app settings, llama-server path, models directory, HF token source.
- **Hugging Face integration** (`hugging_face`, `model_card`) — search GGUF models, validate tokens, fetch model metadata and README cards.
- **Model management** (`model_store`, `model_profiles`) — list local `.gguf` files, save per-model runtime settings.
- **Downloads** (`downloads`) — stream GGUF files from HF with resume support, cancel tokens, and progress events.
- **Server lifecycle** (`llama_process`) — spawn/stop/monitor `llama-server` as a child process with argv construction.
- **Hardware scanning** (`hardware`) — CPU/RAM via `sysinfo`, GPUs via `nvidia-smi` and `/sys/class/drm`, llama device enumeration via `--list-devices`.
- **Recommendations** (`recommendations`) — suggest GPU layers, context size, and thread count based on hardware + model size.
- **Diagnostics** (`diagnostics`) — framework health check (portal status, GPU vendor, Wayland/NVIDIA workarounds).
- **Platform workaround** (`main.rs`) — detects KDE Wayland + NVIDIA and sets `__NV_DISABLE_EXPLICIT_SYNC=1` before the Tauri event loop starts to avoid `Gdk-Message` protocol crashes.

## Design Patterns

- **Command-per-operation IPC**: Every backend operation exposed to the frontend is a `#[tauri::command]` async or sync function registered in a single `generate_handler!` block in `main.rs`. This is the only IPC surface.
- **Mutex-wrapped managed state**: `ConfigState`, `ProfilesState`, `DownloadsState`, `ServerState`, and `WorkaroundState` are inserted into the Tauri app handle at `.setup()` time. Commands access them via `tauri::State<'_, T>`. Lock scope is kept minimal (load, drop, then compute).
- **Module-per-domain**: Each subsystem lives in its own file with a clear split between Tauri-agnostic core logic and Tauri command wrappers. For example, `hugging_face.rs` has pure `async fn search_hf(...)` internals and thin `#[tauri::command]` shims that inject state.
- **File-based JSON persistence**: `config_store` and `model_profiles` read/write `config.json` and `profiles.json` in `app_data_dir()` via `serde_json`. Writes happen immediately on mutation commands.
- **Atomic download writes**: Downloads stream to a `.gguf.download` temp file and are renamed on completion, preventing partial files in the models directory.
- **Event-driven progress**: `downloads` and `llama_process` emit Tauri events (`download-progress`, `server-log`) so the frontend can observe long-running work without polling.
- **Path sandboxing**: `model_store::safe_download_path` validates that downloaded files land inside the configured models directory via `canonicalize` + `starts_with` checks.

## Data & Control Flow

1. **Startup** (`main.rs`):
   - `apply_linux_workarounds()` probes `XDG_SESSION_TYPE` and `/proc/driver/nvidia/version`; if Wayland+NVIDIA and the env var is unset, it sets `__NV_DISABLE_EXPLICIT_SYNC=1`.
   - Tauri builder loads `ConfigState` and `ProfilesState` from disk, inserts default `DownloadsState` and `ServerState`, and registers all commands.

2. **Config flow**:
   - Frontend → `get_config` / `update_config` / `pick_llama_server_executable` / `pick_models_dir`
   - `update_config` locks `ConfigState`, mutates in memory, then calls `save_config` to disk.
   - `resolve_hf_token` reads `HF_TOKEN` env var first, then falls back to the saved token.

3. **HF search & model details**:
   - Frontend → `hf_search(query)` or `hf_model(repo_id)`
   - Commands extract the optional token from `ConfigState`, call pure async helpers that hit `https://huggingface.co/api/models` with `reqwest`.
   - Results are deserialized into `HfSearchResult` / `HfModelInfo` and returned to the frontend.

4. **Download flow**:
   - Frontend → `download_start(repo_id, filename)`
   - Backend computes `safe_download_path`, marks the download active in `DownloadsState`, streams bytes with `reqwest::Response::bytes_stream()`, writes chunks, and emits `download-progress` events.
   - Cancellation is cooperative: `download_cancel` sets a flag in `DownloadsState`; the stream loop checks it between chunks.

5. **Server lifecycle**:
   - Frontend → `server_start(model_path, settings)`
   - `llama_process::build_argv` maps `LlamaSettings` fields to `llama-server` CLI flags (host, port, ctx-size, n-gpu-layers, threads, etc.).
   - A `Child` process is spawned with piped stdout/stderr; an async task reads lines and emits `server-log` events up to `MAX_LOG_LINES`.
   - `server_stop` kills the child. `server_status` returns whether the process is running and the last log lines.

6. **Hardware & recommendations**:
   - `hardware_scan` gathers CPU brand/cores/threads/RAM from `sysinfo`, GPUs from `nvidia-smi` query, and llama devices from `llama-server --list-devices`.
   - `model_recommendation` takes model size + `HardwareInfo` and returns `FitStatus` (GpuLikely, CpuOnly, Unlikely) plus suggested GPU layers, threads, and batch size.

## Integration Points

- **Tauri v2 runtime**: `tauri`, `tauri-build`, `tauri-plugin-dialog` (xdg-portal file picker), `tauri-plugin-shell` (open URLs).
- **Frontend**: All communication is through the Tauri invoke API and event bus. The frontend is built by Vite (`../dist`) and served at `http://localhost:1420` in dev mode.
- **Hugging Face Hub**: REST endpoints for model search (`/api/models?filter=gguf`), model metadata (`/api/models/{repo_id}`), token validation (`/api/whoami-v2`), and raw file downloads (`https://huggingface.co/{repo_id}/resolve/main/{file}`).
- **llama-server binary**: Located via user config; invoked for `--list-devices` and for the actual inference server. Arguments mirror `llama.cpp` server CLI flags.
- **Host GPU stack**: `nvidia-smi` for NVIDIA VRAM; `/sys/class/drm` for AMD/Intel GPU detection; `sysinfo` crate for CPU/memory.
- **Linux desktop portals**: `tauri-plugin-dialog` uses xdg-portal; `diagnostics.rs` probes `/usr/share/xdg-desktop-portal/portals` and DBus reachability to report framework health.

## File Index

| File | Role |
|------|------|
| `Cargo.toml` | Package manifest. Declares Tauri v2, dialog/shell plugins, `reqwest`, `tokio`, `sysinfo`, `serde`, `chrono`, `regex`, `futures-util`. |
| `tauri.conf.json` | Tauri app config. Window size 1100×750, bundle icons, CSP disabled, shell open plugin enabled. |
| `build.rs` | One-liner calling `tauri_build::build()` for asset/codegen. |
| `src/main.rs` | Entry point. Applies Linux workarounds, builds Tauri app with managed state and `generate_handler!` command registration. |
| `src/types.rs` | Shared `Serialize`/`Deserialize` structs: `AppConfig`, `HfSearchResult`, `HfModelInfo`, `DownloadProgress`, `ModelProfile`, `LlamaSettings`, `HardwareInfo`, `ServerStatus`, `FrameworkDiagnostics`, etc. |
| `src/config_store.rs` | Load/save `config.json`, `resolve_hf_token`, file picker commands. |
| `src/model_profiles.rs` | Load/save `profiles.json`, CRUD commands keyed by `model_path[+hf_repo+hf_file]`. |
| `src/hugging_face.rs` | HF API client: search, model detail, token validation, whoami. |
| `src/model_card.rs` | Fetch README + card data, parse setting hints from markdown with regex. |
| `src/model_store.rs` | Recursive `.gguf` listing, path validation, safe download path generation. |
| `src/downloads.rs` | Streaming download with temp-file-then-rename, cancellation flags, progress events. |
| `src/llama_process.rs` | `llama-server` child process spawn/stop/status, argv builder, log capture. |
| `src/hardware.rs` | `sysinfo` scan, `nvidia-smi` parsing, `--list-devices` runner. |
| `src/recommendations.rs` | Heuristic fit estimator based on model size vs available VRAM/RAM. |
| `src/diagnostics.rs` | Portal/GPU/env introspection for troubleshooting reports. |
