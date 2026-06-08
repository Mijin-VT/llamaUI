use crate::config_store::ConfigState;
use crate::types::GgufFileInfo;
use std::path::Path;
use tauri::State;

/// List all .gguf files in the configured models directory
#[tauri::command]
pub fn models_list(state: State<'_, ConfigState>) -> Result<Vec<GgufFileInfo>, String> {
    let config = state.0.lock().map_err(|e| e.to_string())?;
    let models_dir = config.models_dir.as_ref().ok_or("Models directory not configured")?;
    let dir = Path::new(models_dir);

    if !dir.exists() {
        return Err(format!("Models directory does not exist: {}", models_dir));
    }

    let mut files = Vec::new();
    visit_gguf_files(dir, dir, &mut files)?;
    files.sort_by(|a, b| a.rfilename.to_lowercase().cmp(&b.rfilename.to_lowercase()));
    Ok(files)
}

fn visit_gguf_files(base: &Path, current: &Path, files: &mut Vec<GgufFileInfo>) -> Result<(), String> {
    let entries = std::fs::read_dir(current).map_err(|e| e.to_string())?;
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.is_dir() {
            visit_gguf_files(base, &path, files)?;
        } else if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
            if name.to_lowercase().ends_with(".gguf") {
                let relative = path.strip_prefix(base)
                    .unwrap_or(&path)
                    .to_str()
                    .unwrap_or(name)
                    .to_string();
                let size = std::fs::metadata(&path).ok().map(|m| m.len());
                files.push(GgufFileInfo { rfilename: relative, size });
            }
        }
    }
    Ok(())
}

/// Validate that a path is inside the configured models directory
pub fn validate_path_in_models(models_dir: &str, path: &str) -> Result<(), String> {
    let base = std::path::Path::new(models_dir).canonicalize().map_err(|e| format!("Invalid models dir: {}", e))?;
    let target = std::path::Path::new(path).canonicalize().map_err(|e| format!("Invalid target path: {}", e))?;
    if !target.starts_with(&base) {
        return Err("Path is outside the configured models directory".to_string());
    }
    Ok(())
}

/// Generate a safe destination filename from repo_id and filename
pub fn safe_download_path(models_dir: &str, repo_id: &str, filename: &str) -> Result<std::path::PathBuf, String> {
    // Create a subdirectory from the repo_id (namespace--repo format)
    let safe_repo = repo_id.replace('/', "--");
    // Sanitize filename: only keep alphanumeric, dash, underscore, dot
    let safe_name: String = filename.chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' || c == '.' { c } else { '_' })
        .collect();
    let dir = std::path::Path::new(models_dir).join(&safe_repo);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(&safe_name);
    // Verify the final path is still inside models_dir
    validate_path_in_models(models_dir, path.to_str().unwrap_or(""))?;
    Ok(path)
}
