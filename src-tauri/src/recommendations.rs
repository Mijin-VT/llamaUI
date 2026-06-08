use crate::types::HardwareInfo;
use crate::types::{FitStatus, LlamaSettings, ModelRecommendation};

#[tauri::command]
pub fn model_recommendation(
    model_size_bytes: u64,
    hardware: HardwareInfo,
    settings: Option<LlamaSettings>,
) -> Result<ModelRecommendation, String> {
    let ctx_size = settings.as_ref().and_then(|s| s.ctx_size).unwrap_or(4096);
    let threads = settings.as_ref().and_then(|s| s.threads);

    // Estimate total RAM needed: model size + ~20% overhead for KV cache and context
    let overhead_ratio = 1.2;
    let estimated_ram = ((model_size_bytes as f64) * overhead_ratio) as u64;

    // Estimate VRAM needed for full GPU offload: model size + KV cache overhead
    let kv_overhead = estimate_kv_overhead(ctx_size);
    let estimated_vram = model_size_bytes + kv_overhead;

    // Determine fit status
    let free_vram: u64 = hardware.gpus.iter().map(|g| g.vram_free_bytes).sum();
    let has_gpu = !hardware.gpus.is_empty() || !hardware.llama_devices.is_empty();

    let (fit_status, suggested_gpu_layers, use_fit_flag, confidence) = if !has_gpu {
        if hardware.ram_available_bytes >= estimated_ram {
            (FitStatus::CpuOnly, 0, false, "high".to_string())
        } else {
            (FitStatus::Unlikely, 0, false, "medium".to_string())
        }
    } else if free_vram >= estimated_vram {
        (FitStatus::GpuLikely, 99, true, "high".to_string())
    } else if free_vram > 0 {
        // Partial GPU offload
        let ratio = free_vram as f64 / estimated_vram as f64;
        let layers = std::cmp::max(1, (ratio * 99.0) as i32);
        (FitStatus::PartialGpu, layers, true, "medium".to_string())
    } else if hardware.ram_available_bytes >= estimated_ram {
        (FitStatus::CpuOnly, 0, false, "medium".to_string())
    } else {
        (FitStatus::Unlikely, 0, false, "low".to_string())
    };

    let suggested_threads = threads.unwrap_or(std::cmp::min(
        hardware.cpu_threads as u32,
        (hardware.cpu_cores as u32 * 2).min(16),
    ));

    let suggested_batch_size = if has_gpu { 512 } else { 128 };

    let mut notes = Vec::new();
    notes.push(format!("Model file size: {}", format_bytes(model_size_bytes)));
    notes.push(format!(
        "Available RAM: {}",
        format_bytes(hardware.ram_available_bytes)
    ));
    if has_gpu {
        notes.push(format!("Available VRAM: {}", format_bytes(free_vram)));
    }
    match &fit_status {
        FitStatus::GpuLikely => {
            notes.push("Model should fit entirely in GPU memory".to_string())
        }
        FitStatus::PartialGpu => notes.push(format!(
            "Partial GPU offload: ~{} layers suggested",
            suggested_gpu_layers
        )),
        FitStatus::CpuOnly => {
            notes.push("No GPU detected or VRAM insufficient; will run on CPU".to_string())
        }
        FitStatus::Unlikely => {
            notes.push("WARNING: May not have enough RAM to run this model".to_string())
        }
    }
    if use_fit_flag {
        notes.push("Using --fit on is recommended for first run".to_string());
    }

    Ok(ModelRecommendation {
        fit_status,
        confidence,
        estimated_model_size_bytes: model_size_bytes,
        estimated_ram_required_bytes: estimated_ram,
        estimated_vram_required_bytes: estimated_vram,
        suggested_gpu_layers,
        suggested_ctx_size: ctx_size,
        suggested_threads,
        suggested_batch_size,
        use_fit_flag,
        notes,
    })
}

fn estimate_kv_overhead(ctx_size: u64) -> u64 {
    // Rough estimate: ~128 bytes per token per layer for KV cache
    // Using a conservative estimate
    ctx_size * 128
}

fn format_bytes(bytes: u64) -> String {
    const KB: u64 = 1024;
    const MB: u64 = KB * 1024;
    const GB: u64 = MB * 1024;
    if bytes >= GB {
        format!("{:.1} GiB", bytes as f64 / GB as f64)
    } else if bytes >= MB {
        format!("{:.1} MiB", bytes as f64 / MB as f64)
    } else {
        format!("{} bytes", bytes)
    }
}
