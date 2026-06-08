use crate::types::ModelProfile;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{AppHandle, Manager};

pub struct ProfilesState(pub Mutex<HashMap<String, ModelProfile>>);

const PROFILES_FILE: &str = "profiles.json";

fn profiles_path(app: &AppHandle) -> PathBuf {
    app.path().app_data_dir().expect("app data dir").join(PROFILES_FILE)
}

pub fn load_profiles(app: &AppHandle) -> HashMap<String, ModelProfile> {
    let path = profiles_path(app);
    if path.exists() {
        let data = std::fs::read_to_string(&path).unwrap_or_default();
        serde_json::from_str(&data).unwrap_or_default()
    } else {
        HashMap::new()
    }
}

pub fn save_profiles(app: &AppHandle, profiles: &HashMap<String, ModelProfile>) -> Result<(), String> {
    let path = profiles_path(app);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let data = serde_json::to_string_pretty(profiles).map_err(|e| e.to_string())?;
    std::fs::write(&path, data).map_err(|e| e.to_string())
}

/// Generate a profile key from model path and optional HF identity
fn profile_key(model_path: &str, hf_repo: Option<&str>, hf_file: Option<&str>) -> String {
    match (hf_repo, hf_file) {
        (Some(repo), Some(file)) => format!("{}::{}::{}", model_path, repo, file),
        (Some(repo), None) => format!("{}::{}", model_path, repo),
        _ => model_path.to_string(),
    }
}

#[tauri::command]
pub fn model_profile_get(
    state: tauri::State<'_, ProfilesState>,
    model_path: String,
    hf_repo: Option<String>,
    hf_file: Option<String>,
) -> Result<Option<ModelProfile>, String> {
    let profiles = state.0.lock().map_err(|e| e.to_string())?;
    let key = profile_key(&model_path, hf_repo.as_deref(), hf_file.as_deref());
    Ok(profiles.get(&key).cloned())
}

#[tauri::command]
pub fn model_profile_save(
    app: AppHandle,
    state: tauri::State<'_, ProfilesState>,
    profile: ModelProfile,
) -> Result<(), String> {
    let mut profiles = state.0.lock().map_err(|e| e.to_string())?;
    let key = profile_key(&profile.model_path, profile.hf_repo.as_deref(), profile.hf_file.as_deref());
    let mut p = profile;
    p.id = key.clone();
    profiles.insert(key, p);
    save_profiles(&app, &profiles)
}

#[tauri::command]
pub fn model_profile_delete(
    app: AppHandle,
    state: tauri::State<'_, ProfilesState>,
    model_path: String,
    hf_repo: Option<String>,
    hf_file: Option<String>,
) -> Result<(), String> {
    let mut profiles = state.0.lock().map_err(|e| e.to_string())?;
    let key = profile_key(&model_path, hf_repo.as_deref(), hf_file.as_deref());
    profiles.remove(&key);
    save_profiles(&app, &profiles)
}

#[tauri::command]
pub fn model_profile_list(
    state: tauri::State<'_, ProfilesState>,
) -> Result<Vec<ModelProfile>, String> {
    let profiles = state.0.lock().map_err(|e| e.to_string())?;
    Ok(profiles.values().cloned().collect())
}
