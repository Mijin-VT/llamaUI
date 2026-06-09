# `src/pages` Codemap

This folder contains the top-level page components rendered inside `App.tsx`. Each page is a self-contained React functional component that owns its local UI state and communicates with the Tauri backend through `../shared/tauriApi`.

---

## Responsibility

| Module | Responsibility |
|--------|----------------|
| `SetupPage.tsx` | Edit and persist application configuration: llama-server executable path, models directory, host/port, Hugging Face token, and one-off hardware scan. Validates/saves the HF token and surfaces hardware info. |
| `DownloadPage.tsx` | Search Hugging Face for GGUF models, list results with expandable file rows, start/cancel downloads, and forward selected repo/model to other pages via callbacks. |
| `HfModelPage.tsx` | Show detailed model-card metadata and README for a selected HF repo, list individual GGUF/`mmproj` files with per-file download controls, and apply model-card setting hints to the Run page. |
| `RunPage.tsx` | Select a local GGUF model, pick or save per-model profiles, tune quick/advanced `llama-server` settings, check hardware fit/recommendations, preview the generated command, and start/stop/restart the server. |
| `StatusPage.tsx` | Monitor the running server: fetch status, display PID/health/command, render live log stream with auto-scroll, and provide stop/refresh/clear controls. |
| `DiagnosticsPage.tsx` | One-shot framework diagnostics used to verify native toolkit/portal/GPU state on the host. |

---

## Design Patterns

### Component model
- Every page is a default-exported functional component receiving props from `App.tsx`.
- No class components; all state is `useState`, side effects are `useEffect`, and expensive derivations use `useMemo`/`useCallback`.

### State ownership
- **Global/shared state lives in `App.tsx`:** current page, `AppConfig`, selected HF repo, selected model path, and pending setting hints.
- **Page-local state owns everything else:** form fields, search results, download progress, logs, server status, hardware scan output, recommendations.

### Lifecycle & cleanup
- Event listeners from Tauri (`onDownloadProgress`, `onServerLog`, `onServerStarted`) return an `unlisten` function that is captured in a ref/local variable and invoked in the effect cleanup.
- Polling intervals (`StatusPage` health poll, `RunPage` status poll) are stored in refs and cleared on dependency change/unmount.
- Race-guard pattern with a `cancelled` boolean inside effects that fetch data (`HfModelPage`, `DownloadPage` listener setup).

### Optimistic / incremental UI
- `DownloadPage` and `HfModelPage` immediately insert a placeholder progress entry when a download starts, then merge real events from the backend.
- `StatusPage` backfills the log buffer from the initial `serverStatus` snapshot if the client-side log array is empty.

### Derived values
- Badges, health labels, command-line previews, file filtering (`gguf`/`mmproj`), and category-grouped option lists are computed during render or via `useMemo`.

### Controlled inputs
- All form fields (text, number, select, checkbox, password) are controlled components bound to React state.

### Local helpers & sub-components
- `RunPage` defines `OptionControl` to render a single `llama-server` option by type (boolean/number/string).
- `HfModelPage` defines `FileRow` to keep the per-file download UI isolated.
- `DownloadPage` uses an inner `renderFile` function instead of a separate component.

### Visual conventions
- Every page renders inside a wrapper with `className="page ..."`.
- Common layout primitives reused across pages: `card`, `card-header`, `card-body`, `callout callout-error/warn`, `flex-row`, `hint`, `badge-*`, `btn btn-sm`, `mono`.

---

## Data & Control Flow

### `App.tsx` orchestration
- Holds `AppSharedState` (`config`, `selectedHfRepo`, `selectedModelPath`, `appliedHints`).
- Mount: calls `getConfig()` once to hydrate `config`.
- Navigation is imperative via callbacks passed to pages:
  - `DownloadPage.onSelectRepo(repoId)` → sets repo and switches to `hf-model`.
  - `DownloadPage.onSelectModel(path)` → sets model path and switches to `run`.
  - `HfModelPage.onApplyHints(hints)` → stores hints; `HfModelPage.onGoToRun()` → switches to `run`.
  - `SetupPage.onConfigUpdate(config)` → updates shared `config`.
- `RunPage` receives `appliedHints` and `onAppliedHintsConsumed`; it applies hints in a one-shot effect and clears them.

### Backend command flow (pages → Tauri)
- `SetupPage` → `pickLlamaServerExecutable`, `pickModelsDir`, `hardwareScan`, `hfValidateToken`, `hfWhoami`, `updateConfig`.
- `DownloadPage` → `hfSearch`, `downloadStart`, `downloadCancel`, `modelsList`.
- `HfModelPage` → `hfModelCard`, `hfModel`, `downloadStart`, `downloadCancel`, `modelsList`.
- `RunPage` → `modelsList`, `modelProfileList`, `modelProfileSave`, `modelRecommendation`, `serverStart`, `serverStop`, `serverStatus`, `hardwareScan`.
- `StatusPage` → `serverStatus`, `serverStop`.
- `DiagnosticsPage` → `frameworkDiagnostics`.

### Backend event flow (Tauri → pages)
- `onDownloadProgress` is listened to by both `DownloadPage` and `HfModelPage` to update download UIs.
- `onServerLog` streams log lines into `StatusPage` with a `MAX_LOG_LINES` ring buffer.
- `onServerStarted` triggers a status refresh in `StatusPage`.

### Page-specific flows
- **SetupPage:** Mirrors `config` prop into local form state with a sync effect. `buildConfig()` constructs the canonical `AppConfig`; `persistConfig()` calls `updateConfig` then notifies the parent.
- **DownloadPage:** `doSearch` fills `results`; `toggleExpand` manages which repos show file lists; `startDownload`/`cancelDownload` mutate a `Map<string, DownloadProgress>` keyed by `repoId::filename`; `refreshLocalFiles` cross-references `modelsList` to show checkmarks.
- **HfModelPage:** On `repoId` change, runs `Promise.all([hfModelCard(repoId), hfModel(repoId)])`. Splits siblings into regular GGUF and `mmproj` files. Applies setting hints by invoking the `onApplyHints` + `onGoToRun` callbacks.
- **RunPage:** Loads models on mount; loads profiles whenever `selectedModel` changes; merges profile settings over `config.global_defaults`. Settings are edited directly; `buildCommandArgv` iterates `LLAMA_OPTIONS` to produce a command preview. Fit check calls `modelRecommendation` with the selected model size, hardware, and current settings.
- **StatusPage:** Auto-polls status every 5 s while running; auto-scrolls the log panel unless the user manually scrolls away (`handleLogScroll` toggles `autoScrollRef`).

---

## Integration Points

### Shared modules
- `../shared/tauriApi` — command/event facade used by every page.
- `../shared/types` — TypeScript types (`AppConfig`, `LlamaSettings`, `ModelProfile`, `DownloadProgress`, `ServerStatus`, etc.).
- `../shared/llamaOptions` — option metadata (`LLAMA_OPTIONS`, categories, types, tooltips) consumed by `RunPage` to render controls and build the CLI.

### Parent coupling
- All pages receive `config: AppConfig | null` from `App.tsx`.
- Pages that influence navigation receive callbacks defined in `App.tsx` (`onSelectRepo`, `onSelectModel`, `onApplyHints`, `onGoToRun`, `onConfigUpdate`, `onAppliedHintsConsumed`).

### External UI library
- `HfModelPage` renders the model-card README with `react-markdown` + `remark-gfm`.

### Browser UX
- `StatusPage` and `RunPage` render external links to the running llama-server web UI using the host/port from `config`/`settings`.

### Conventions observed by all pages
- Import React hooks explicitly from `react`.
- Use `useCallback` for handlers passed to child helpers or event listeners.
- Use `useRef` for any value that must be stable across renders (unlisten handles, interval IDs, auto-scroll flag).
- Errors are captured in page-local `error` state and rendered as `callout callout-error`.
