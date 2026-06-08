use crate::config_store::{resolve_hf_token, ConfigState};
use crate::model_store::safe_download_path;
use crate::types::DownloadProgress;
use std::collections::HashMap;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, State};

pub struct DownloadsState {
    pub active: Mutex<HashMap<String, bool>>, // download_id -> cancelled
}

impl Default for DownloadsState {
    fn default() -> Self {
        Self {
            active: Mutex::new(HashMap::new()),
        }
    }
}

fn make_download_id(repo_id: &str, filename: &str) -> String {
    format!("{}::{}", repo_id, filename)
}

#[tauri::command]
pub async fn download_start(
    app: AppHandle,
    config_state: State<'_, ConfigState>,
    downloads_state: State<'_, DownloadsState>,
    repo_id: String,
    filename: String,
) -> Result<DownloadProgress, String> {
    let (models_dir, token) = {
        let guard = config_state.0.lock().map_err(|e| e.to_string())?;
        let dir = guard.models_dir.clone().ok_or("Models directory not configured")?;
        let tok = resolve_hf_token(&*guard);
        (dir, tok)
    };

    let dest = safe_download_path(&models_dir, &repo_id, &filename)?;
    let id = make_download_id(&repo_id, &filename);

    // Mark as active (not cancelled)
    downloads_state
        .active
        .lock()
        .map_err(|e| e.to_string())?
        .insert(id.clone(), false);

    let url = format!(
        "https://huggingface.co/{}/resolve/main/{}",
        repo_id, filename
    );
    let client = reqwest::Client::new();
    let mut req = client.get(&url);
    if let Some(t) = &token {
        req = req.header("Authorization", format!("Bearer {}", t));
    }

    let resp = req.send().await.map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        downloads_state
            .active
            .lock()
            .map_err(|e| e.to_string())?
            .remove(&id);
        return Err(format!("HTTP {} downloading {}", resp.status(), filename));
    }

    let total_size = resp.content_length();

    // Write to temp file first, then rename
    let temp_path = dest.with_extension("gguf.download");
    let mut file = std::fs::File::create(&temp_path).map_err(|e| e.to_string())?;
    let mut downloaded: u64 = 0;

    let mut stream = resp.bytes_stream();
    use futures_util::StreamExt;

    while let Some(chunk) = stream.next().await {
        // Check cancellation
        let cancelled = downloads_state
            .active
            .lock()
            .map_err(|e| e.to_string())?
            .get(&id)
            .copied()
            .unwrap_or(true);
        if cancelled {
            drop(file);
            let _ = std::fs::remove_file(&temp_path);
            downloads_state
                .active
                .lock()
                .map_err(|e| e.to_string())?
                .remove(&id);
            return Err("Download cancelled".to_string());
        }

        let chunk = chunk.map_err(|e| e.to_string())?;
        std::io::Write::write_all(&mut file, &chunk).map_err(|e| e.to_string())?;
        downloaded += chunk.len() as u64;

        // Emit progress event
        let progress = DownloadProgress {
            id: id.clone(),
            repo_id: repo_id.clone(),
            filename: filename.clone(),
            bytes_downloaded: downloaded,
            bytes_total: total_size,
            done: false,
            error: None,
        };
        let _ = app.emit("download-progress", &progress);
    }

    drop(file);
    std::fs::rename(&temp_path, &dest).map_err(|e| e.to_string())?;
    downloads_state
        .active
        .lock()
        .map_err(|e| e.to_string())?
        .remove(&id);

    let result = DownloadProgress {
        id: id.clone(),
        repo_id: repo_id.clone(),
        filename: filename.clone(),
        bytes_downloaded: downloaded,
        bytes_total: total_size,
        done: true,
        error: None,
    };
    let _ = app.emit("download-progress", &result);
    Ok(result)
}

#[tauri::command]
pub fn download_cancel(
    state: State<'_, DownloadsState>,
    repo_id: String,
    filename: String,
) -> Result<(), String> {
    let id = make_download_id(&repo_id, &filename);
    let mut active = state.active.lock().map_err(|e| e.to_string())?;
    if let Some(cancelled) = active.get_mut(&id) {
        *cancelled = true;
    }
    Ok(())
}

#[tauri::command]
pub fn download_status(
    state: State<'_, DownloadsState>,
    repo_id: String,
    filename: String,
) -> Result<bool, String> {
    let id = make_download_id(&repo_id, &filename);
    let active = state.active.lock().map_err(|e| e.to_string())?;
    Ok(active.contains_key(&id))
}
