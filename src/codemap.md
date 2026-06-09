# `src/` — React Frontend (Tauri WebView Layer)

## Responsibility

This directory contains the entire browser-side UI of the LlamUI desktop application. It is a React + TypeScript SPA rendered inside a Tauri WebView. Its job is to:

1. **Render the shell** — tab navigation bar + main content area.
2. **Orchestrate cross-page state** — `AppConfig`, selected HF repo / local model, and setting hints from model cards.
3. **Surface Tauri commands** — every backend interaction flows through `shared/tauriApi.ts`.
4. **Present six functional pages** — setup, model discovery/download, model detail, run configuration, server status, and framework diagnostics.

There is no routing library; page switching is handled by a single string enum in `App.tsx` with conditional rendering.

---

## Design Patterns

### Lifted-State "Router"
`App.tsx` owns two pieces of state:
- `page: 'setup' | 'download' | 'hf-model' | 'run' | 'status' | 'diagnostics'`
- `shared: AppSharedState` (`config`, `selectedHfRepo`, `selectedModelPath`, `appliedHints`)

Child pages never change their own URL; they call callbacks (`onSelectRepo`, `onSelectModel`, `onGoToRun`, etc.) that mutate the shared state **and** flip the active page. This couples data selection with navigation.

### Thin Tauri Abstraction (`shared/tauriApi.ts`)
Every Rust command is wrapped in a typed `async` function that calls `@tauri-apps/api/core` `invoke`. Event streams (download progress, server logs, server-started) use `listen<T>(event, handler)` and return `UnlistenFn`. All types are imported from `shared/types.ts`, which are explicit mirrors of the Rust types in `src-tauri/src/types.rs`.

### Declarative CLI-to-Settings Mapping (`shared/llamaOptions.ts`)
`LLAMA_OPTIONS` is a static array of metadata objects describing every `llama-server` CLI flag the UI exposes. Each entry declares:
- `flag`, `aliases`, `valueType`, `category`, `tooltip`
- `settingKey?: keyof LlamaSettings` — links the flag to a typed config field
- `restartRequired: boolean`

`RunPage` uses this array to dynamically render form controls and to build the final `argv` array passed to `serverStart`.

### Page-Local State with Callback Side-Effects
Pages manage their own fetching, polling, and ephemeral UI state (search queries, download progress maps, log buffers). When a user action needs to affect another page (e.g., picking a model on **Download** should open **Run**), the page calls a prop callback that mutates the parent state and triggers a re-render onto the new page.

---

## Data & Control Flow

### Entry Point
**`src/main.tsx`**
- Creates a React root on `#root`.
- Imports global `styles.css`.
- Renders `<App />` inside `React.StrictMode`.

### Root Orchestrator
**`src/App.tsx`**
1. **Mount effect** → calls `getConfig()` and stores the result in `shared.config`.
2. **Tab bar** → renders six nav buttons; clicking one sets `page` directly.
3. **Conditional page render** — inside `<main>`, a chain of `page === 'x' && <PageX ... />` guards renders exactly one page at a time.
4. **Shared-state callbacks**:
   - `updateConfig(config)` → overwrites `shared.config`
   - `selectHfRepo(repoId)` → sets `shared.selectedHfRepo` **and** switches to `hf-model`
   - `selectModel(path)` → sets `shared.selectedModelPath` **and** switches to `run`
   - `applyHints(hints)` / `clearAppliedHints()` → sets / clears `shared.appliedHints`
   - `goToRun()` → simply switches to `run`

### Pages (control flow summaries)

| Page | Key State | Key Tauri Calls | Notable Flow |
|------|-----------|-----------------|--------------|
| **`SetupPage`** | `llama_server_path`, `models_dir`, `hf_token_source`, hardware scan result | `pickLlamaServerExecutable`, `pickModelsDir`, `hfValidateToken`, `hfWhoami`, `hardwareScan`, `updateConfig` | File-picker dialogs return paths that are immediately persisted via `updateConfig`. Token source is rendered as a badge (none / env_var / saved). |
| **`DownloadPage`** | Search query, `HfSearchResult[]`, local `GgufFileInfo[]`, active download map | `hfSearch`, `downloadStart`, `downloadCancel`, `onDownloadProgress`, `modelsList` | Search results and local models are shown side-by-side. Selecting a repo calls `onSelectRepo`; selecting a local model calls `onSelectModel`. Downloads are keyed by `repoId::filename`. |
| **`HfModelPage`** | `repoId`, model card markdown, sibling files, per-file download state | `hfModelCard`, `hfModel`, download APIs same as above | Reads `repoId` from shared state. Renders README with `react-markdown`. GGUF files can be downloaded **or** their card hints can be applied and the user sent to **Run** via `onGoToRun`. |
| **`RunPage`** | Selected model path, `LlamaSettings`, profile (load/save), hardware info, recommendation, command preview | `modelsList`, `modelProfileGet`, `modelProfileSave`, `hardwareScan`, `modelRecommendation`, `serverStart` | The most complex page. Loads all local models into a dropdown. When a model is selected, it fetches/creates a profile, scans hardware, requests a `ModelRecommendation`, and merges hints from the model card (`appliedHints`). Builds a live `argv` preview from `LLAMA_OPTIONS`. Starting the server calls `serverStart(modelPath, settings)`. |
| **`StatusPage`** | `ServerStatus`, log lines array (`MAX_LOG_LINES = 500`), health poll timer | `serverStatus`, `serverStop`, `onServerLog`, `onServerStarted` | On mount: listens to `server-log` and `server-started` events. Polls `serverStatus` every 5 s while running. Auto-scrolls logs unless the user manually scrolls up. |
| **`DiagnosticsPage`** | `FrameworkDiagnostics` | `frameworkDiagnostics` | One-shot fetch on mount + manual refresh. Displays a static grid of environment / GPU / portal / workaround fields used to validate KDE Wayland + NVIDIA viability. |

---

## Integration Points

### Upstream — Tauri Backend (`src-tauri/src/`)
All backend integration is funneled through **`shared/tauriApi.ts`**. The modules it talks to are:
- `config_store.rs` — `get_config`, `update_config`
- `downloads.rs` — `download_start`, `download_cancel`, `download_status`
- `hugging_face.rs` — `hf_search`, `hf_model`, `hf_model_card`, `hf_validate_token`, `hf_whoami`
- `model_store.rs` / `model_profiles.rs` — `models_list`, `model_profile_get/save/delete/list`
- `hardware.rs` — `hardware_scan`
- `recommendations.rs` — `model_recommendation`
- `llama_process.rs` — `server_start`, `server_stop`, `server_status`
- `diagnostics.rs` — `framework_diagnostics`

Event channels:
- `download-progress` → `DownloadPage`, `HfModelPage`
- `server-log` → `StatusPage`
- `server-started` → `StatusPage`

### Downstream — `index.html` / Vite
`index.html` (repo root) loads the Vite-bundled script. `src/main.tsx` is the Vite entry point. `src/styles.css` is imported globally and provides the CSS custom-property theming and layout rules consumed by all pages.

### Cross-Page Data Contract (`AppSharedState`)
```ts
interface AppSharedState {
  config: AppConfig | null;
  selectedHfRepo: string | null;
  selectedModelPath: string | null;
  appliedHints: SettingHint[] | null;
}
```
- `config` is required by nearly every page (paths, host/port, token).
- `selectedHfRepo` is write-only from **Download**, read-only by **HfModel**.
- `selectedModelPath` is write-only from **Download** (local model) or from **HfModel** after download, read-only by **Run**.
- `appliedHints` is write-only from **HfModel**, read-and-clear by **Run** (consumed once when the model is selected).

### Shared Modules
- **`shared/types.ts`** — canonical TypeScript shapes for every DTO. Kept in sync manually with Rust.
- **`shared/llamaOptions.ts`** — single source of truth for `llama-server` flag metadata. Imported only by `RunPage`.
- **`shared/tauriApi.ts`** — no page imports Tauri APIs directly; everything goes through here.
