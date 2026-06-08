use crate::types::{AppConfig, HfTokenSource};
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{AppHandle, Manager};

pub struct ConfigState(pub Mutex<AppConfig>);

const CONFIG_FILE: &str = "config.json";

fn config_path(app: &AppHandle) -> PathBuf {
    app.path().app_data_dir().expect("app data dir").join(CONFIG_FILE)
}

pub fn load_config(app: &AppHandle) -> AppConfig {
    let path = config_path(app);
    if path.exists() {
        let data = std::fs::read_to_string(&path).unwrap_or_default();
        let mut config: AppConfig = serde_json::from_str(&data).unwrap_or_default();
        config.apply_defaults();
        // Check if HF_TOKEN is set in env and token source is None
        if matches!(config.hf_token_source, HfTokenSource::None) && std::env::var("HF_TOKEN").is_ok() {
            config.hf_token_source = HfTokenSource::EnvVar;
        }
        config
    } else {
        let mut config = AppConfig::default();
        config.apply_defaults();
        if std::env::var("HF_TOKEN").is_ok() {
            config.hf_token_source = HfTokenSource::EnvVar;
        }
        config
    }
}

pub fn save_config(app: &AppHandle, config: &AppConfig) -> Result<(), String> {
    let path = config_path(app);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let data = serde_json::to_string_pretty(config).map_err(|e| e.to_string())?;
    std::fs::write(&path, data).map_err(|e| e.to_string())
}

/// Resolve the effective HF token: env var > saved > none
pub fn resolve_hf_token(config: &AppConfig) -> Option<String> {
    if let Ok(token) = std::env::var("HF_TOKEN") {
        return Some(token);
    }

    match &config.hf_token_source {
        HfTokenSource::Saved(token) => Some(token.clone()),
        HfTokenSource::EnvVar | HfTokenSource::None => None,
    }
}

// Tauri commands:
#[tauri::command]
pub fn get_config(state: tauri::State<'_, ConfigState>) -> Result<AppConfig, String> {
    let config = state.0.lock().map_err(|e| e.to_string())?;
    Ok(config.clone())
}

#[tauri::command]
pub fn update_config(app: AppHandle, state: tauri::State<'_, ConfigState>, config: AppConfig) -> Result<(), String> {
    let mut current = state.0.lock().map_err(|e| e.to_string())?;
    *current = config.clone();
    save_config(&app, &config)
}

#[tauri::command]
pub async fn pick_llama_server_executable(app: AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let path = app.dialog().file().blocking_pick_file();
    Ok(path.map(|p| p.to_string()))
}

#[tauri::command]
pub async fn pick_models_dir(app: AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let path = app.dialog().file().blocking_pick_folder();
    Ok(path.map(|p| p.to_string()))
}
