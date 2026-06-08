use crate::config_store::{resolve_hf_token, ConfigState};
use crate::types::{HfCardData, ModelCardResponse, SettingHint};
use regex::Regex;
use tauri::{AppHandle, State};

/// Fetch the raw README.md content from HF
async fn fetch_readme(repo_id: &str, token: Option<&str>) -> Option<String> {
    let url = format!("https://huggingface.co/{}/raw/main/README.md", repo_id);
    let client = reqwest::Client::new();
    let mut req = client.get(&url);
    if let Some(t) = token {
        req = req.header("Authorization", format!("Bearer {}", t));
    }
    let resp = req.send().await.ok()?;
    if resp.status().is_success() {
        Some(resp.text().await.ok()?)
    } else {
        None
    }
}

/// Fetch model card data from the API
async fn fetch_card_data(repo_id: &str, token: Option<&str>) -> Option<HfCardData> {
    let url = format!("https://huggingface.co/api/models/{}", repo_id);
    let client = reqwest::Client::new();
    let mut req = client.get(&url);
    if let Some(t) = token {
        req = req.header("Authorization", format!("Bearer {}", t));
    }
    let resp = req.send().await.ok()?;
    if resp.status().is_success() {
        let val: serde_json::Value = resp.json().await.ok()?;
        Some(
            serde_json::from_value(val.get("cardData").cloned().unwrap_or_default()).ok()?,
        )
    } else {
        None
    }
}

/// Parse explicit llama.cpp setting hints from the README text
fn parse_setting_hints(readme: &str) -> Vec<SettingHint> {
    let mut hints = Vec::new();
    // Look for common patterns like: `-c 4096` or `--ctx-size 4096` or `-ngl 99` or `--n-gpu-layers 99`
    let patterns = [
        (r"(?m)(?:-c|--ctx-size)\s+(\d+)", "ctx-size"),
        (
            r"(?m)(?:-ngl|--n-gpu-layers|--gpu-layers)\s+(-?\d+)",
            "n-gpu-layers",
        ),
        (r"(?m)(?:-t|--threads)\s+(\d+)", "threads"),
        (r"(?m)(?:-b|--batch-size)\s+(\d+)", "batch-size"),
        (r"(?m)(?:--temp)\s+([\d.]+)", "temp"),
        (r"(?m)(?:-p|--parallel)\s+(\d+)", "parallel"),
    ];
    for (pat, key) in patterns {
        if let Ok(re) = Regex::new(pat) {
            if let Some(caps) = re.captures(readme) {
                if let Some(m) = caps.get(1) {
                    hints.push(SettingHint {
                        key: key.to_string(),
                        value: m.as_str().to_string(),
                        source: "model_card".to_string(),
                    });
                }
            }
        }
    }
    hints
}

#[tauri::command]
pub async fn hf_model_card(
    _app: AppHandle,
    state: State<'_, ConfigState>,
    repo_id: String,
) -> Result<ModelCardResponse, String> {
    let token = {
        let guard = state.0.lock().map_err(|e| e.to_string())?;
        resolve_hf_token(&*guard)
    };

    let (readme, card_data) = tokio::join!(
        fetch_readme(&repo_id, token.as_deref()),
        fetch_card_data(&repo_id, token.as_deref())
    );

    let suggested_settings = readme
        .as_ref()
        .map(|r| parse_setting_hints(r))
        .unwrap_or_default();

    Ok(ModelCardResponse {
        repo_id,
        readme,
        card_data,
        suggested_settings: if suggested_settings.is_empty() {
            None
        } else {
            Some(suggested_settings)
        },
    })
}
