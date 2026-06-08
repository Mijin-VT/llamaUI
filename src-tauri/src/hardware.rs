use crate::config_store::ConfigState;
use crate::types::{GpuInfo, HardwareInfo, LlamaDevice};
use std::process::Command;
use tauri::State;

#[tauri::command]
pub fn hardware_scan(state: State<'_, ConfigState>) -> Result<HardwareInfo, String> {
    let config = state.0.lock().map_err(|e| e.to_string())?;
    let llama_path = config.llama_server_path.clone();
    drop(config);

    // System info via sysinfo crate
    let mut sys = sysinfo::System::new_all();
    sys.refresh_all();

    let cpu_model = sys
        .cpus()
        .first()
        .map(|c| c.brand().to_string())
        .unwrap_or_else(|| "Unknown".to_string());
    let cpu_cores = sys.physical_core_count().unwrap_or(0);
    let cpu_threads = sys.cpus().len();
    let ram_total = sys.total_memory();
    let ram_available = sys.available_memory();

    // Try to detect GPUs from system info
    let gpus = detect_gpus();

    // Try llama-server --list-devices if path is configured
    let llama_devices = llama_path
        .as_ref()
        .map(|path| run_list_devices(path))
        .unwrap_or(Ok(vec![]))
        .unwrap_or_default();

    Ok(HardwareInfo {
        cpu_model,
        cpu_cores,
        cpu_threads,
        ram_total_bytes: ram_total,
        ram_available_bytes: ram_available,
        gpus,
        llama_devices,
    })
}

fn detect_gpus() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    // Try nvidia-smi for NVIDIA GPUs
    if let Ok(output) = Command::new("nvidia-smi")
        .args([
            "--query-gpu=name,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ])
        .output()
    {
        if output.status.success() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            for line in stdout.lines() {
                let parts: Vec<&str> = line.split(',').collect();
                if parts.len() >= 3 {
                    let name = parts[0].trim().to_string();
                    let vram_total = parts[1].trim().parse::<u64>().unwrap_or(0) * 1024 * 1024;
                    let vram_free = parts[2].trim().parse::<u64>().unwrap_or(0) * 1024 * 1024;
                    gpus.push(GpuInfo {
                        name,
                        vram_total_bytes: vram_total,
                        vram_free_bytes: vram_free,
                    });
                }
            }
        }
    }

    gpus
}

fn run_list_devices(llama_path: &str) -> Result<Vec<LlamaDevice>, String> {
    let output = Command::new(llama_path)
        .arg("--list-devices")
        .output()
        .map_err(|e| format!("Failed to run --list-devices: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut devices = Vec::new();

    // Parse output like: "0: NVIDIA GeForce RTX 4090, 24576 MiB"
    for (i, line) in stdout.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if let Some(rest) = line.strip_prefix(&format!("{}: ", i)) {
            let name = rest.split(',').next().unwrap_or(rest).trim().to_string();
            let vram = rest
                .split(',')
                .nth(1)
                .and_then(|s| s.trim().split(' ').next())
                .and_then(|s| s.parse::<u64>().ok())
                .map(|v| v * 1024 * 1024);
            devices.push(LlamaDevice {
                index: i as u32,
                name,
                vram_total_bytes: vram,
                vram_free_bytes: None,
            });
        }
    }

    Ok(devices)
}
