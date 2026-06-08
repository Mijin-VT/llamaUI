use serde::{Deserialize, Serialize};

// --- Config ---

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct AppConfig {
    pub llama_server_path: Option<String>,
    pub models_dir: Option<String>,
    pub host: String,
    pub port: u16,
    pub hf_token_source: HfTokenSource,
    pub global_defaults: Option<LlamaSettings>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(rename_all = "snake_case")]
pub enum HfTokenSource {
    None,
    EnvVar,
    Saved(String),
}

impl Default for HfTokenSource {
    fn default() -> Self {
        Self::None
    }
}

impl AppConfig {
    pub fn apply_defaults(&mut self) {
        if self.host.is_empty() {
            self.host = "127.0.0.1".into();
        }
        if self.port == 0 {
            self.port = 8080;
        }
    }
}

// --- HF types ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct HfSearchResult {
    pub id: String,
    pub downloads: i64,
    pub likes: i64,
    pub tags: Vec<String>,
    pub gated: bool,
    pub private: bool,
    pub gguf_files: Vec<GgufFileInfo>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct GgufFileInfo {
    pub rfilename: String,
    pub size: Option<u64>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct HfModelInfo {
    pub id: String,
    pub sha: Option<String>,
    pub downloads: i64,
    pub likes: i64,
    pub tags: Vec<String>,
    pub gated: bool,
    pub private: bool,
    pub siblings: Vec<HfSibling>,
    pub card_data: Option<HfCardData>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct HfSibling {
    pub rfilename: String,
    pub size: Option<u64>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct HfCardData {
    pub pipeline_tag: Option<String>,
    pub base_model: Option<String>,
    pub license: Option<String>,
    pub model_type: Option<String>,
    pub library_name: Option<String>,
    pub language: Option<Vec<String>>,
    pub tags: Option<Vec<String>>,
}

// --- Model card ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ModelCardResponse {
    pub repo_id: String,
    pub readme: Option<String>,
    pub card_data: Option<HfCardData>,
    pub suggested_settings: Option<Vec<SettingHint>>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct SettingHint {
    pub key: String,
    pub value: String,
    pub source: String,
}

// --- Downloads ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct DownloadProgress {
    pub id: String,
    pub repo_id: String,
    pub filename: String,
    pub bytes_downloaded: u64,
    pub bytes_total: Option<u64>,
    pub done: bool,
    pub error: Option<String>,
}


// --- Model profiles ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ModelProfile {
    pub id: String,
    pub model_path: String,
    pub hf_repo: Option<String>,
    pub hf_file: Option<String>,
    pub settings: LlamaSettings,
    pub name: String,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct LlamaSettings {
    pub ctx_size: Option<u64>,
    pub n_gpu_layers: Option<i32>,
    pub threads: Option<u32>,
    pub batch_size: Option<u64>,
    pub ubatch_size: Option<u64>,
    pub parallel: Option<u32>,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub mmap: Option<bool>,
    pub mlock: Option<bool>,
    pub verbose: Option<bool>,
    pub temp: Option<f32>,
    pub top_k: Option<u32>,
    pub top_p: Option<f32>,
    pub min_p: Option<f32>,
    pub repeat_penalty: Option<f32>,
    pub seed: Option<u64>,
    pub hf_repo: Option<String>,
    pub hf_file: Option<String>,
    pub extra_args: Option<Vec<String>>,
}

// --- Hardware ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct HardwareInfo {
    pub cpu_model: String,
    pub cpu_cores: usize,
    pub cpu_threads: usize,
    pub ram_total_bytes: u64,
    pub ram_available_bytes: u64,
    pub gpus: Vec<GpuInfo>,
    pub llama_devices: Vec<LlamaDevice>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct GpuInfo {
    pub name: String,
    pub vram_total_bytes: u64,
    pub vram_free_bytes: u64,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct LlamaDevice {
    pub index: u32,
    pub name: String,
    pub vram_total_bytes: Option<u64>,
    pub vram_free_bytes: Option<u64>,
}

// --- Recommendations ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ModelRecommendation {
    pub fit_status: FitStatus,
    pub confidence: String,
    pub estimated_model_size_bytes: u64,
    pub estimated_ram_required_bytes: u64,
    pub estimated_vram_required_bytes: u64,
    pub suggested_gpu_layers: i32,
    pub suggested_ctx_size: u64,
    pub suggested_threads: u32,
    pub suggested_batch_size: u64,
    pub use_fit_flag: bool,
    pub notes: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub enum FitStatus {
    GpuLikely,
    PartialGpu,
    CpuOnly,
    Unlikely,
}

// --- Server status ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct ServerStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub command: Option<String>,
    pub health: Option<String>,
    pub log_lines: Vec<String>,
    pub started_at: Option<String>,
}

// --- Framework diagnostics ---

#[derive(Serialize, Deserialize, Clone, Debug)]
pub enum GpuVendor {
    Nvidia,
    Amd,
    Intel,
    Unknown,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct WorkaroundInputs {
    pub xdg_session_type: Option<String>,
    pub nvidia_driver_present: bool,
    pub env_already_set: bool,
    pub set_by_us: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct FrameworkDiagnostics {
    pub framework: String,
    pub dialog_backend: String,
    pub xdg_session_type: Option<String>,
    pub xdg_current_desktop: Option<String>,
    pub desktop_session: Option<String>,
    pub gdk_backend: Option<String>,
    pub wayland_display: Option<String>,
    pub display: Option<String>,
    pub qt_qpa_platform: Option<String>,
    pub portal_descriptors: Vec<String>,
    pub active_portal_name: Option<String>,
    pub portal_dbus_reachable: bool,
    pub gpu_vendor: GpuVendor,
    pub gpu_driver_version: Option<String>,
    pub nvidia_driver_present: bool,
    pub explicit_sync_disabled: bool,
    pub workaround_applied: bool,
    pub workaround_inputs: WorkaroundInputs,
}
