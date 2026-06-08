use crate::config_store::{resolve_hf_token, ConfigState};
use crate::types::*;
use serde::Deserialize;
use tauri::AppHandle;
use reqwest::header::{AUTHORIZATION, HeaderValue};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Build a reqwest client, optionally attaching a Bearer token.
fn build_client(token: Option<&str>) -> Result<reqwest::Client, String> {
    let mut headers = reqwest::header::HeaderMap::new();
    if let Some(t) = token {
        let val = HeaderValue::from_str(&format!("Bearer {t}")).map_err(|e| e.to_string())?;
        headers.insert(AUTHORIZATION, val);
    }
    reqwest::Client::builder()
        .default_headers(headers)
        .build()
        .map_err(|e| e.to_string())
}

/// Resolve the effective HF token from ConfigState (locks, reads, drops).
fn token_from_state(state: &tauri::State<'_, ConfigState>) -> Option<String> {
    let guard = state.0.lock().ok()?;
    resolve_hf_token(&guard)
}

// ---------------------------------------------------------------------------
// HF API deserialization shims
// ---------------------------------------------------------------------------

/// Raw shape returned by `GET /api/models?filter=gguf&search=…`.
#[derive(Deserialize)]
struct HfSearchItem {
    id: String,
    #[serde(default)]
    downloads: i64,
    #[serde(default)]
    likes: i64,
    #[serde(default)]
    tags: Vec<String>,
    #[serde(default)]
    gated: bool,
    #[serde(default)]
    private: bool,
    #[serde(default)]
    siblings: Vec<HfSiblingRaw>,
}

#[derive(Deserialize)]
struct HfSiblingRaw {
    rfilename: String,
    #[serde(default)]
    size: Option<u64>,
}

/// Raw shape returned by `GET /api/models/{repo_id}`.
#[derive(Deserialize)]
struct HfModelResponse {
    id: String,
    #[serde(default)]
    sha: Option<String>,
    #[serde(default)]
    downloads: i64,
    #[serde(default)]
    likes: i64,
    #[serde(default)]
    tags: Vec<String>,
    #[serde(default)]
    gated: bool,
    #[serde(default)]
    private: bool,
    #[serde(default)]
    siblings: Vec<HfSiblingRaw>,
    #[serde(default)]
    #[serde(alias = "cardData")]
    card_data: Option<HfCardDataRaw>,
}

#[derive(Deserialize)]
struct HfCardDataRaw {
    #[serde(rename = "pipeline_tag")]
    pipeline_tag: Option<String>,
    #[serde(rename = "base_model")]
    base_model: Option<serde_json::Value>,
    license: Option<String>,
    #[serde(rename = "model_type")]
    model_type: Option<String>,
    #[serde(rename = "library_name")]
    library_name: Option<String>,
    language: Option<serde_json::Value>,
    tags: Option<Vec<String>>,
}


// ---------------------------------------------------------------------------
// Core logic (no Tauri dependency)
// ---------------------------------------------------------------------------

/// Search Hugging Face for GGUF models.
pub async fn search_hf(
    query: &str,
    token: Option<&str>,
) -> Result<Vec<HfSearchResult>, String> {
    let client = build_client(token)?;
    let url = reqwest::Url::parse_with_params(
        "https://huggingface.co/api/models",
        &[
            ("filter", "gguf"),
            ("search", query),
            ("sort", "downloads"),
            ("direction", "-1"),
            ("limit", "30"),
            ("full", "true"),
        ],
    ).map_err(|e| format!("URL build error: {e}"))?;

    let resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("HF search request failed: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("HF search returned status {}", resp.status()));
    }

    let items: Vec<HfSearchItem> = resp.json().await.map_err(|e| format!("HF search parse error: {e}"))?;

    let results = items
        .into_iter()
        .map(|item| {
            let gguf_files: Vec<GgufFileInfo> = item
                .siblings
                .iter()
                .filter(|s| {
                    let name = s.rfilename.to_lowercase();
                    name.ends_with(".gguf")
                        && !name.contains("mmproj")
                })
                .map(|s| GgufFileInfo {
                    rfilename: s.rfilename.clone(),
                    size: s.size,
                })
                .collect();

            // Also include mmproj*.gguf files so the UI can offer them.
            let mmproj_files: Vec<GgufFileInfo> = item
                .siblings
                .iter()
                .filter(|s| {
                    let name = s.rfilename.to_lowercase();
                    name.ends_with(".gguf") && name.contains("mmproj")
                })
                .map(|s| GgufFileInfo {
                    rfilename: s.rfilename.clone(),
                    size: s.size,
                })
                .collect();

            let mut all_gguf = gguf_files;
            all_gguf.extend(mmproj_files);

            HfSearchResult {
                id: item.id,
                downloads: item.downloads,
                likes: item.likes,
                tags: item.tags,
                gated: item.gated,
                private: item.private,
                gguf_files: all_gguf,
            }
        })
        .filter(|r| !r.gguf_files.is_empty())
        .collect();

    Ok(results)
}

/// Fetch detailed model info for a specific repo.
pub async fn get_hf_model(
    repo_id: &str,
    token: Option<&str>,
) -> Result<HfModelInfo, String> {
    let client = build_client(token)?;
    let repo_path = validated_repo_path(repo_id)?;
    let url = format!("https://huggingface.co/api/models/{repo_path}");

    let resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("HF model request failed: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!(
            "HF model info returned status {} for {repo_id}",
            resp.status()
        ));
    }

    let raw: HfModelResponse = resp.json().await.map_err(|e| format!("HF model parse error: {e}"))?;

    let siblings = raw
        .siblings
        .into_iter()
        .map(|s| HfSibling {
            rfilename: s.rfilename,
            size: s.size,
        })
        .collect();


    let card_data = raw.card_data.map(|cd| {
        // HF sometimes returns `language` as a string instead of an array.
        let language = match cd.language {
            Some(serde_json::Value::Array(arr)) => Some(
                arr.into_iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect(),
            ),
            Some(serde_json::Value::String(s)) => Some(vec![s]),
            _ => None,
        };

        let base_model = match cd.base_model {
            Some(serde_json::Value::String(s)) => Some(s),
            Some(serde_json::Value::Array(arr)) => arr
                .into_iter()
                .find_map(|v| v.as_str().map(|s| s.to_string())),
            _ => None,
        };

        HfCardData {
            pipeline_tag: cd.pipeline_tag,
            base_model,
            license: cd.license,
            model_type: cd.model_type,
            library_name: cd.library_name,
            language,
            tags: cd.tags,
        }
    });

    Ok(HfModelInfo {
        id: raw.id,
        sha: raw.sha,
        downloads: raw.downloads,
        likes: raw.likes,
        tags: raw.tags,
        gated: raw.gated,
        private: raw.private,
        siblings,
        card_data,
    })
}

fn validated_repo_path(repo_id: &str) -> Result<&str, String> {
    if repo_id.is_empty()
        || repo_id.starts_with('/')
        || repo_id.ends_with('/')
        || repo_id.contains("..")
        || repo_id.contains('\\')
        || repo_id.contains('?')
        || repo_id.contains('#')
    {
        return Err(format!("Invalid HF repo id: {repo_id}"));
    }
    Ok(repo_id)
}


/// Validate an HF token by calling the whoami endpoint.
pub async fn validate_hf_token(token: &str) -> Result<String, String> {
    let client = build_client(Some(token))?;
    let resp = client
        .get("https://huggingface.co/api/whoami-v2")
        .send()
        .await
        .map_err(|e| format!("HF whoami request failed: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("Invalid token (status {})", resp.status()));
    }

    let body: serde_json::Value = resp.json().await.map_err(|e| format!("HF whoami parse error: {e}"))?;

    // The whoami-v2 response has { name, fullname, ... }
    let name = body
        .get("name")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .or_else(|| {
            body.get("fullname")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .ok_or_else(|| "Unexpected whoami response format".to_string())?;

    Ok(name)
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub async fn hf_validate_token(token: String) -> Result<String, String> {
    validate_hf_token(token.trim()).await
}

#[tauri::command]
pub async fn hf_whoami(
    _app: AppHandle,
    state: tauri::State<'_, ConfigState>,
) -> Result<Option<String>, String> {
    let token = token_from_state(&state);
    match token {
        Some(t) => {
            let name = validate_hf_token(&t).await?;
            Ok(Some(name))
        }
        None => Ok(None),
    }
}

#[tauri::command]
pub async fn hf_search(
    _app: AppHandle,
    state: tauri::State<'_, ConfigState>,
    query: String,
) -> Result<Vec<HfSearchResult>, String> {
    let token = token_from_state(&state);
    let token_ref = token.as_deref();
    search_hf(&query, token_ref).await
}

#[tauri::command]
pub async fn hf_model(
    _app: AppHandle,
    state: tauri::State<'_, ConfigState>,
    repo_id: String,
) -> Result<HfModelInfo, String> {
    let token = token_from_state(&state);
    let token_ref = token.as_deref();
    get_hf_model(&repo_id, token_ref).await
}
