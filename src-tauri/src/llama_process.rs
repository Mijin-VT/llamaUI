use crate::config_store::ConfigState;
use crate::types::{LlamaSettings, ServerStatus};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};

pub struct ServerState {
    pub child: Mutex<Option<Child>>,
    pub logs: Mutex<Vec<String>>,
    pub command: Mutex<Option<String>>,
    pub started_at: Mutex<Option<String>>,
}

impl Default for ServerState {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            logs: Mutex::new(Vec::new()),
            command: Mutex::new(None),
            started_at: Mutex::new(None),
        }
    }
}

const MAX_LOG_LINES: usize = 500;

/// Build the argv array from model path and settings
pub fn build_argv(
    _llama_server_path: &str,
    model_path: &str,
    settings: &LlamaSettings,
    default_host: &str,
    default_port: u16,
) -> Vec<String> {
    let mut args = vec!["-m".to_string(), model_path.to_string()];

    // Host/port
    let host = settings.host.as_deref().unwrap_or(default_host);
    let port = settings.port.unwrap_or(default_port);
    args.extend(["--host".to_string(), host.to_string()]);
    args.extend(["--port".to_string(), port.to_string()]);

    // Core settings
    if let Some(v) = settings.ctx_size { args.extend(["--ctx-size".to_string(), v.to_string()]); }
    if let Some(v) = settings.n_gpu_layers { args.extend(["--n-gpu-layers".to_string(), v.to_string()]); }
    if let Some(v) = settings.threads { args.extend(["--threads".to_string(), v.to_string()]); }
    if let Some(v) = settings.batch_size { args.extend(["--batch-size".to_string(), v.to_string()]); }
    if let Some(v) = settings.ubatch_size { args.extend(["--ubatch-size".to_string(), v.to_string()]); }
    if let Some(v) = settings.parallel { args.extend(["--parallel".to_string(), v.to_string()]); }

    // Boolean flags
    match settings.mmap {
        Some(false) => args.push("--no-mmap".to_string()),
        Some(true) => { /* --mmap is default */ }
        None => {}
    }
    if settings.mlock.unwrap_or(false) { args.push("--mlock".to_string()); }
    if settings.verbose.unwrap_or(false) { args.push("--verbose".to_string()); }

    // Sampling
    if let Some(v) = settings.temp { args.extend(["--temp".to_string(), v.to_string()]); }
    if let Some(v) = settings.top_k { args.extend(["--top-k".to_string(), v.to_string()]); }
    if let Some(v) = settings.top_p { args.extend(["--top-p".to_string(), v.to_string()]); }
    if let Some(v) = settings.min_p { args.extend(["--min-p".to_string(), v.to_string()]); }
    if let Some(v) = settings.repeat_penalty { args.extend(["--repeat-penalty".to_string(), v.to_string()]); }
    if let Some(v) = settings.seed { args.extend(["--seed".to_string(), v.to_string()]); }

    // HF direct loading
    if let Some(v) = &settings.hf_repo { args.extend(["--hf-repo".to_string(), v.clone()]); }
    if let Some(v) = &settings.hf_file { args.extend(["--hf-file".to_string(), v.clone()]); }

    // Extra args
    if let Some(extra) = &settings.extra_args {
        args.extend(extra.iter().cloned());
    }

    args
}

/// Spawn llama-server with the given arguments
#[tauri::command]
pub async fn server_start(
    app: AppHandle,
    config_state: State<'_, ConfigState>,
    server_state: State<'_, ServerState>,
    model_path: String,
    settings: LlamaSettings,
) -> Result<(), String> {
    let config = config_state.0.lock().map_err(|e| e.to_string())?;
    let llama_path = config.llama_server_path.clone().ok_or("llama-server path not configured")?;
    let host = config.host.clone();
    let port = config.port;
    drop(config);

    // Stop any existing server
    stop_server(&server_state)?;

    let args = build_argv(&llama_path, &model_path, &settings, &host, port);
    let cmd_str = format!("{} {}", llama_path, args.join(" "));

    let mut child = Command::new(&llama_path)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start llama-server: {}", e))?;

    // Store command string
    *server_state.command.lock().map_err(|e| e.to_string())? = Some(cmd_str);
    *server_state.started_at.lock().map_err(|e| e.to_string())? = Some(chrono::Utc::now().to_rfc3339());

    // Spawn log readers
    let pid = child.id();
    if let Some(stdout) = child.stdout.take() {
        let app_clone = app.clone();
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(line) = line {
                    let _ = app_clone.emit("server-log", &line);
                    if let Ok(mut logs) = app_clone.state::<ServerState>().logs.lock() {
                        logs.push(line);
                        if logs.len() > MAX_LOG_LINES {
                            let excess = logs.len() - MAX_LOG_LINES;
                            logs.drain(0..excess);
                        }
                    }
                }
            }
        });
    }
    if let Some(stderr) = child.stderr.take() {
        let app_clone = app.clone();
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    let _ = app_clone.emit("server-log", &line);
                    if let Ok(mut logs) = app_clone.state::<ServerState>().logs.lock() {
                        logs.push(line);
                        if logs.len() > MAX_LOG_LINES {
                            let excess = logs.len() - MAX_LOG_LINES;
                            logs.drain(0..excess);
                        }
                    }
                }
            }
        });
    }

    *server_state.child.lock().map_err(|e| e.to_string())? = Some(child);

    let _ = app.emit("server-started", pid);
    Ok(())
}

fn stop_server(server_state: &State<'_, ServerState>) -> Result<(), String> {
    let mut child_lock = server_state.child.lock().map_err(|e| e.to_string())?;
    if let Some(child) = child_lock.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *child_lock = None;
    server_state.command.lock().map_err(|e| e.to_string())?.take();
    server_state.started_at.lock().map_err(|e| e.to_string())?.take();
    Ok(())
}

#[tauri::command]
pub fn server_stop(server_state: State<'_, ServerState>) -> Result<(), String> {
    stop_server(&server_state)
}

#[tauri::command]
pub async fn server_status(
    _app: AppHandle,
    server_state: State<'_, ServerState>,
    config_state: State<'_, ConfigState>,
) -> Result<ServerStatus, String> {
    let (host, port) = {
        let guard = config_state.0.lock().map_err(|e| e.to_string())?;
        (guard.host.clone(), guard.port)
    };

    let (running, pid) = {
        let guard = server_state.child.lock().map_err(|e| e.to_string())?;
        (guard.is_some(), guard.as_ref().map(|c| c.id()))
    };

    let command = server_state.command.lock().map_err(|e| e.to_string())?.clone();
    let started_at = server_state.started_at.lock().map_err(|e| e.to_string())?.clone();

    // Check health endpoint
    let health = if running {
        let url = format!("http://{}:{}/health", host, port);
        match reqwest::get(&url).await {
            Ok(resp) if resp.status().is_success() => {
                let body: serde_json::Value = resp.json().await.unwrap_or_default();
                body.get("status").and_then(|v| v.as_str()).unwrap_or("unknown").to_string()
            }
            Ok(resp) => format!("http_{}", resp.status()),
            Err(_) => "unreachable".to_string(),
        }
    } else {
        "stopped".to_string()
    };

    let logs = server_state.logs.lock().map_err(|e| e.to_string())?.clone();

    Ok(ServerStatus {
        running,
        pid,
        command,
        health: Some(health),
        log_lines: logs,
        started_at,
    })
}
