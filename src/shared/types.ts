// TypeScript types mirroring Rust types in src-tauri/src/types.rs

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export type HfTokenSource = "none" | "env_var" | { saved: string };

export interface AppConfig {
  llama_server_path?: string;
  models_dir?: string;
  host: string;
  port: number;
  hf_token_source: HfTokenSource;
  global_defaults?: LlamaSettings;
}

// ---------------------------------------------------------------------------
// Hugging Face search / model info
// ---------------------------------------------------------------------------

export interface GgufFileInfo {
  rfilename: string;
  size?: number;
}

export interface HfSearchResult {
  id: string;
  downloads: number;
  likes: number;
  tags: string[];
  gated: boolean;
  private: boolean;
  gguf_files: GgufFileInfo[];
}

export interface HfSibling {
  rfilename: string;
  size?: number;
}

export interface HfCardData {
  pipeline_tag?: string;
  base_model?: string;
  license?: string;
  model_type?: string;
  library_name?: string;
  language?: string[];
  tags?: string[];
}

export interface HfModelInfo {
  id: string;
  sha?: string;
  downloads: number;
  likes: number;
  tags: string[];
  gated: boolean;
  private: boolean;
  siblings: HfSibling[];
  card_data?: HfCardData;
}

// ---------------------------------------------------------------------------
// Model card
// ---------------------------------------------------------------------------

export interface SettingHint {
  key: string;
  value: string;
  source: string;
}

export interface ModelCardResponse {
  repo_id: string;
  readme?: string;
  card_data?: HfCardData;
  suggested_settings?: SettingHint[];
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------

export interface DownloadProgress {
  id: string;
  repo_id: string;
  filename: string;
  bytes_downloaded: number;
  bytes_total?: number;
  done: boolean;
  error?: string;
}

export interface DownloadRequest {
  repo_id: string;
  filename: string;
}

// ---------------------------------------------------------------------------
// Model profiles & llama-server settings
// ---------------------------------------------------------------------------

export interface LlamaSettings {
  ctx_size?: number;
  n_gpu_layers?: number;
  threads?: number;
  batch_size?: number;
  ubatch_size?: number;
  parallel?: number;
  host?: string;
  port?: number;
  mmap?: boolean;
  mlock?: boolean;
  verbose?: boolean;
  temp?: number;
  top_k?: number;
  top_p?: number;
  min_p?: number;
  repeat_penalty?: number;
  seed?: number;
  hf_repo?: string;
  hf_file?: string;
  extra_args?: string[];
}

export interface ModelProfile {
  id: string;
  model_path: string;
  hf_repo?: string;
  hf_file?: string;
  settings: LlamaSettings;
  name: string;
}

// ---------------------------------------------------------------------------
// Hardware
// ---------------------------------------------------------------------------

export interface GpuInfo {
  name: string;
  vram_total_bytes: number;
  vram_free_bytes: number;
}

export interface LlamaDevice {
  index: number;
  name: string;
  vram_total_bytes?: number;
  vram_free_bytes?: number;
}

export interface HardwareInfo {
  cpu_model: string;
  cpu_cores: number;
  cpu_threads: number;
  ram_total_bytes: number;
  ram_available_bytes: number;
  gpus: GpuInfo[];
  llama_devices: LlamaDevice[];
}

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------

export type FitStatus =
  | "GpuLikely"
  | "PartialGpu"
  | "CpuOnly"
  | "Unlikely";

export interface ModelRecommendation {
  fit_status: FitStatus;
  confidence: string;
  estimated_model_size_bytes: number;
  estimated_ram_required_bytes: number;
  estimated_vram_required_bytes: number;
  suggested_gpu_layers: number;
  suggested_ctx_size: number;
  suggested_threads: number;
  suggested_batch_size: number;
  use_fit_flag: boolean;
  notes: string[];
}

// ---------------------------------------------------------------------------
// Server status
// ---------------------------------------------------------------------------

export interface ServerStatus {
  running: boolean;
  pid?: number;
  command?: string;
  health?: string;
  log_lines: string[];
  started_at?: string;
}

// ---------------------------------------------------------------------------
// Framework diagnostics
// ---------------------------------------------------------------------------

export type GpuVendor = "Nvidia" | "Amd" | "Intel" | "Unknown";

export interface WorkaroundInputs {
  xdg_session_type?: string;
  nvidia_driver_present: boolean;
  env_already_set: boolean;
  set_by_us: boolean;
}

export interface FrameworkDiagnostics {
  framework: string;
  dialog_backend: string;
  xdg_session_type?: string;
  xdg_current_desktop?: string;
  desktop_session?: string;
  gdk_backend?: string;
  wayland_display?: string;
  display?: string;
  qt_qpa_platform?: string;
  portal_descriptors: string[];
  active_portal_name?: string;
  portal_dbus_reachable: boolean;
  gpu_vendor: GpuVendor;
  gpu_driver_version?: string;
  nvidia_driver_present: boolean;
  explicit_sync_disabled: boolean;
  workaround_applied: boolean;
  workaround_inputs: WorkaroundInputs;
}
