# `src-tauri/src/` Codemap

## Responsibility

The Tauri backend is the privileged bridge between the React frontend and the host system. It handles:

- **Application lifecycle** (`main.rs`): Bootstraps the Tauri runtime, registers command handlers, initializes shared state, and applies Linux-specific workarounds (NVIDIA + Wayland explicit-sync disable).
- **Shared contracts** (`types.rs`): Central schema for all cross-boundary data — config, Hugging Face API types, download progress, model profiles, hardware info, server status, and framework diagnostics. Every struct is `Serialize + Deserialize` for JSON IPC.
- **Configuration persistence** (`config_store.rs`): Loads/saves `AppConfig` to `app_data_dir()/config.json` with default injection (`host`, `port`). Resolves the effective HF token from env-var override → saved token → none. Exposes native file/folder pickers via `tauri-plugin-dialog`.
- **Hugging Face API client** (`hugging_face.rs`): Searches the HF model hub (`/api/models?filter=gguf`), fetches model metadata and sibling files, and validates tokens via `whoami`. Internal `search_hf`/`get_hf_model` functions are pure async logic; Tauri command wrappers inject `ConfigState` to resolve tokens.
- **Model card extraction** (`model_card.rs`): Fetches `README.md` and card JSON from HF, then regex-parses common `llama.cpp` CLI hints (e.g. `-c 4096`, `--n-gpu-layers 99`) from the readme text.
- **Download manager** (`downloads.rs`): Streams GGUF files from `cdn-lfs.huggingface.co` into temp files (`*.gguf.download`) with atomic rename on completion. Emits `download-progress` events. Cancellation is cooperative: a shared `HashMap<download_id, cancelled>` is checked per chunk.
- **Local model store** (`model_store.rs`): Recursively lists `.gguf` files under the configured `models_dir`, returning relative paths and sizes. Enforces path containment with `canonicalize` checks. Generates safe download destinations (`repo_id` → sanitized subdirectory + sanitized filename).
- **Model profiles** (`model_profiles.rs`): Persistent per-model settings (`LlamaSettings`) keyed by `model_path` + optional `hf_repo`/`hf_file`. Stored in `profiles.json` under the app data dir.
- **Hardware introspection** (`hardware.rs`): Queries `sysinfo` for CPU/RAM, `nvidia-smi` for GPU VRAM, and `llama-server --list-devices` for backend-reported compute devices.
- **Runtime recommendations** (`recommendations.rs`): Heuristic fit analysis comparing model size + KV-cache overhead against available RAM/VRAM. Returns `FitStatus` (GpuLikely / PartialGpu / CpuOnly / Unlikely) and suggested `LlamaSettings`.
- **Llama-server process manager** (`llama_process.rs`): Spawns `llama-server` as a child process, builds argv from `LlamaSettings`, captures stdout/stderr into a rotating 500-line buffer, and emits `server-log` events. Exposes `server_status` which probes the `/health` endpoint and reports PID, command string, and log tail.
- **Framework diagnostics** (`diagnostics.rs`): Linux-only environment probe for troubleshooting portal/DBus/GPU issues. Reads `/sys/class/drm` for GPU vendor PCI IDs, pings the XDG Desktop Portal, and reports whether the NVIDIA explicit-sync workaround was applied.

## Design Patterns

- **Tauri State Management**: Mutable shared state is wrapped in a struct containing `std::sync::Mutex<T>` and registered via `app.manage()` during setup. Commands receive `tauri::State<'_, XState>` to access config, profiles, downloads, server process, and workaround inputs. Lock poisoning is mapped to `String` errors with `.map_err(|e| e.to_string())?`.
- **Command / Core split**: Heavy logic (HF search, model metadata fetch, argv building) lives in pure async or sync functions without Tauri dependencies. The `#[tauri::command]` wrappers are thin adapters that extract state, resolve tokens, and forward to core logic. This keeps the business logic testable and frontend-agnostic.
- **Event emission for push data**: Long-running or streaming operations (downloads, server logs) do not rely solely on invoke/response. `AppHandle::emit` pushes `download-progress` and `server-log` events to the frontend in real time.
- **Atomic file writes**: Downloads write to a temp file with a distinct extension and `std::fs::rename` to the final name only after the stream completes. This prevents partial/corrupted GGUF files in the models directory.
- **Defensive path containment**: `model_store::validate_path_in_models` uses `canonicalize` to ensure any resolved download path is physically inside the configured models directory, preventing directory-traversal from malicious repo IDs or filenames.
- **Option-heavy settings**: `LlamaSettings` uses `Option<T>` for every field so that `build_argv` can omit defaults and let `llama-server` use its own built-in defaults. The frontend only sends overrides.
- **Workaround encapsulation**: Linux GPU/portal quirks are isolated in `main.rs` (apply at startup) and `diagnostics.rs` (report at runtime). The `WorkaroundState` snapshot is captured early and passed into diagnostics so the frontend can see whether the env var was set by the app or pre-existing.

## Data & Control Flow

1. **Startup** (`main.rs`):
   - `apply_linux_workarounds()` reads `XDG_SESSION_TYPE` and `/proc/driver/nvidia/version`, conditionally sets `__NV_DISABLE_EXPLICIT_SYNC`.
   - Loads `config.json` → `ConfigState`, `profiles.json` → `ProfilesState`, empty `DownloadsState`, empty `ServerState`, `WorkaroundState`.
   - Registers all `#[tauri::command]` handlers in a single `generate_handler!` macro invocation.

2. **Configuration flow**:
   - Frontend calls `get_config` / `update_config`.
   - `update_config` writes through the mutex and immediately persists to `config.json` via `serde_json::to_string_pretty`.
   - `resolve_hf_token` reads `HF_TOKEN` env var first, falling back to `config.hf_token_source`.

3. **HF discovery flow**:
   - `hf_search(query)` → `token_from_state` → `search_hf` → `reqwest` to `huggingface.co/api/models` → returns `Vec<HfSearchResult>` with `GgufFileInfo` siblings.
   - `hf_model(repo_id)` → `get_hf_model` → fetches full model metadata + card data.
   - `hf_model_card(repo_id)` → fetches raw README + card JSON, regex-parses setting hints → `ModelCardResponse`.

4. **Download flow**:
   - `download_start(repo_id, filename)` resolves `models_dir` and token from `ConfigState`.
   - Computes `safe_download_path` (sanitizes repo_id and filename, validates containment).
   - Streams response bytes; on each chunk, checks the `active` HashMap for cancellation, then emits `download-progress` with accumulated bytes.
   - On completion: renames `.gguf.download` → `.gguf`, removes the active entry, emits final progress event.
   - `download_cancel` sets the active HashMap flag to true; the next chunk read aborts the stream.

5. **Local model listing**:
   - `models_list` reads `ConfigState` for `models_dir`, walks the directory recursively collecting `.gguf` files, sorts case-insensitively by relative filename.

6. **Profile CRUD**:
   - Key is derived from `model_path` + optional `hf_repo` + `hf_file` (`profile_key`).
   - All mutations lock `ProfilesState`, update the in-memory HashMap, and immediately flush to `profiles.json`.

7. **Server lifecycle**:
   - `server_start(model_path, settings)` stops any existing server, builds argv via `build_argv`, spawns `llama-server` with piped stdout/stderr.
   - Two threads drain pipes, emitting `server-log` events and appending to a rotating `Vec<String>` capped at `MAX_LOG_LINES`.
   - `server_stop` kills the child, clears command/started_at.
   - `server_status` reports PID, command string, log tail, and probes `http://{host}:{port}/health`.

8. **Hardware / recommendation flow**:
   - `hardware_scan` queries `sysinfo`, `nvidia-smi`, and optionally `llama-server --list-devices`.
   - `model_recommendation(model_size_bytes, hardware, settings)` estimates KV overhead from `ctx_size`, sums free VRAM across GPUs, and selects a `FitStatus` with suggested layers, threads, and batch size.

9. **Diagnostics flow**:
   - `framework_diagnostics` reads env vars, scans `/sys/class/drm/device/vendor`, lists portal descriptors, probes DBus, and packages everything into `FrameworkDiagnostics`.

## Integration Points

- **Tauri runtime & plugins**:
  - `tauri::Builder` — app shell, state management, invoke handler registration.
  - `tauri_plugin_dialog` — native file/folder pickers (`pick_llama_server_executable`, `pick_models_dir`).
  - `tauri_plugin_shell` — available but not directly used in this layer (process spawning uses `std::process::Command`).

- **Frontend (React/TypeScript)**:
  - Commands are invoked from `src/shared/tauriApi.ts` and consumed by pages in `src/pages/`.
  - Events listened to: `download-progress`, `server-log`, `server-started`.

- **Hugging Face Hub**:
  - `https://huggingface.co/api/models` — search and model metadata.
  - `https://huggingface.co/{repo_id}/raw/main/README.md` — model card readme.
  - `https://cdn-lfs.huggingface.co` — direct GGUF LFS download.

- **External binaries**:
  - `llama-server` (user-configured path) — spawned as child process; expected to expose `--list-devices` and an HTTP `/health` endpoint.
  - `nvidia-smi` — queried for GPU name and VRAM stats.
  - `dbus-send` — probed to verify XDG Desktop Portal reachability.

- **Host filesystem**:
  - `app.path().app_data_dir()` — stores `config.json` and `profiles.json`.
  - User-configured `models_dir` — stores `.gguf` files and downloaded models.
  - `/sys/class/drm`, `/proc/driver/nvidia/version` — Linux GPU diagnostics.

- **Rust ecosystem dependencies**:
  - `serde` / `serde_json` — all IPC and persistence serialization.
  - `reqwest` + `futures_util` — async HTTP for HF API and downloads.
  - `sysinfo` — CPU, RAM, and process info.
  - `regex` — parsing llama.cpp hints from README text.
  - `chrono` — timestamping server start.
