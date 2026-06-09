# `src/shared` Codemap

## Responsibility

This folder contains the TypeScript frontend’s **shared kernel**: type definitions, the Tauri IPC gateway, and the canonical schema for `llama-server` CLI options. Nothing in here renders UI; every page and component depends on these exports.

| File | Role |
|------|------|
| `types.ts` | TypeScript interfaces that mirror the Rust structs in `src-tauri/src/types.rs`. Single source of truth for cross-layer contracts. |
| `tauriApi.ts` | Thin wrapper around `@tauri-apps/api/core::invoke` and `@tauri-apps/api/event::listen`. Exposes one async function per Tauri command and one listener per backend event. |
| `llamaOptions.ts` | Declarative schema (`LLAMA_OPTIONS`) describing every `llama-server` CLI flag the UI exposes, including type, category, default, tooltip, and mapping to `LlamaSettings` keys. |

---

## Design Patterns

**Mirror Types (types.ts)**
- Every interface is a 1:1 TypeScript representation of a Rust struct in `src-tauri/src/types.rs`. This eliminates serialization surprises at the IPC boundary. Complex unions are minimal (e.g., `HfTokenSource = "none" | "env_var" | { saved: string }`).

**Command Gateway (tauriApi.ts)**
- One function per Tauri command string. Functions are grouped by domain (Config, HF, Downloads, Models, Profiles, Hardware, Recommendations, Server, Diagnostics).
- Event listeners use `listen<T>(eventName, handler)` and return `Promise<UnlistenFn>`, letting callers manage subscription lifetimes.
- No business logic: each function is a pass-through `invoke("cmd", { args })`.

**Schema-as-Data (llamaOptions.ts)**
- `LLAMA_OPTIONS` is a read-only array of `LlamaOption` objects. UI controls are derived from this schema rather than hard-coded per flag.
- `settingKey?: keyof LlamaSettings` creates a type-safe bridge between CLI flags and the persisted settings object.
- `restartRequired` boolean drives UI affordances (e.g., warning that a server restart is needed).
- Categories (`model`, `performance`, `server`, `sampling`, `advanced`) partition options in the settings UI.

---

## Data & Control Flow

**Rust → TypeScript (invoke responses)**
`tauriApi.ts` functions call `invoke("<cmd>")`, which serializes Rust return values into the TypeScript types declared in `types.ts`. Callers await the Promise and receive fully typed objects (e.g., `HardwareInfo`, `DownloadProgress`).

**TypeScript → Rust (invoke arguments)**
Arguments are passed as plain objects. `types.ts` ensures the payload shape matches what the Rust command handlers expect.

**Rust → TypeScript (events)**
The backend emits three events:
- `download-progress` → `onDownloadProgress`
- `server-log` → `onServerLog`
- `server-started` → `onServerStarted`

Listeners are set up in consuming pages/components and torn down on unmount.

**Settings ↔ CLI Flags (llamaOptions.ts)**
1. User edits a setting in the UI.
2. The setting key is looked up in `LLAMA_OPTIONS` to find the corresponding flag, value type, and default.
3. The value is stored in a `LlamaSettings` object.
4. When starting the server, the settings object is passed via `serverStart(modelPath, settings)`, and the Rust backend maps `LlamaSettings` fields back to `llama-server` CLI arguments.

---

## Integration Points

| Consumer | What it imports | Why |
|----------|----------------|-----|
| `src/pages/*.tsx` | `tauriApi.ts` functions + `types.ts` interfaces | Pages issue commands and render typed data. |
| `src-tauri/src/*.rs` | `types.rs` structs | Rust backend defines the canonical types; `types.ts` mirrors them. |
| Settings / Run pages | `LLAMA_OPTIONS` + `LlamaSettings` | Build dynamic forms and validate inputs against the CLI schema. |
| `@tauri-apps/api/core` | `invoke` | Underlying IPC transport; wrapped by `tauriApi.ts`. |
| `@tauri-apps/api/event` | `listen`, `UnlistenFn` | Underlying event transport; wrapped by `tauriApi.ts` listener factories. |

### Key Exported Symbols
- `types.ts`: `AppConfig`, `LlamaSettings`, `ModelProfile`, `HardwareInfo`, `DownloadProgress`, `ServerStatus`, `FrameworkDiagnostics`, `HfSearchResult`, `HfModelInfo`, `ModelRecommendation`, `GpuVendor`, `FitStatus`.
- `tauriApi.ts`: `getConfig`, `updateConfig`, `hfSearch`, `hfModel`, `downloadStart`, `onDownloadProgress`, `serverStart`, `serverStop`, `serverStatus`, `onServerLog`, `onServerStarted`, `hardwareScan`, `modelRecommendation`, `frameworkDiagnostics`, plus profile CRUD (`modelProfileGet`, `modelProfileSave`, `modelProfileDelete`, `modelProfileList`).
- `llamaOptions.ts`: `LLAMA_OPTIONS`, `LlamaOption`, `OptionCategory`, `OptionValueType`.
