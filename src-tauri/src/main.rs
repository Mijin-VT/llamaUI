#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod types;
mod config_store;
mod model_profiles;
mod hugging_face;
mod model_card;
mod model_store;
mod downloads;
mod llama_process;
mod hardware;
mod recommendations;
mod diagnostics;

use tauri::Manager;


/// Keep the WebKitGTK window usable on the observed KDE Wayland + NVIDIA stack.
///
/// The app previously crashed before rendering with:
/// `Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display`.
/// Set this in-process so users do not need to launch through `GDK_BACKEND=x11`,
/// which also bypasses the desktop portal path needed for KDE-native dialogs.
fn apply_linux_workarounds() -> types::WorkaroundInputs {
    let xdg_session_type = std::env::var("XDG_SESSION_TYPE").ok();
    let nvidia_driver_present = std::path::Path::new("/proc/driver/nvidia/version").exists();
    let env_already_set = std::env::var("__NV_DISABLE_EXPLICIT_SYNC").is_ok();
    let set_by_us = xdg_session_type.as_deref() == Some("wayland")
        && nvidia_driver_present
        && !env_already_set;

    if set_by_us {
        std::env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
    }

    types::WorkaroundInputs {
        xdg_session_type,
        nvidia_driver_present,
        env_already_set,
        set_by_us,
    }
}

fn main() {
    let workaround_inputs = apply_linux_workarounds();
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let config = config_store::load_config(&app.handle().clone());
            app.manage(config_store::ConfigState(std::sync::Mutex::new(config)));
            
            let profiles = model_profiles::load_profiles(&app.handle().clone());
            app.manage(model_profiles::ProfilesState(std::sync::Mutex::new(profiles)));
            
            app.manage(downloads::DownloadsState::default());
            app.manage(llama_process::ServerState::default());
            app.manage(diagnostics::WorkaroundState(std::sync::Mutex::new(workaround_inputs)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // Config
            config_store::get_config,
            config_store::update_config,
            config_store::pick_llama_server_executable,
            config_store::pick_models_dir,
            // HF
            hugging_face::hf_validate_token,
            hugging_face::hf_whoami,
            hugging_face::hf_search,
            hugging_face::hf_model,
            // Model card
            model_card::hf_model_card,
            // Downloads
            downloads::download_start,
            downloads::download_cancel,
            downloads::download_status,
            // Models
            model_store::models_list,
            // Profiles
            model_profiles::model_profile_get,
            model_profiles::model_profile_save,
            model_profiles::model_profile_delete,
            model_profiles::model_profile_list,
            // Hardware
            hardware::hardware_scan,
            // Recommendations
            recommendations::model_recommendation,
            // Server
            // Diagnostics
            diagnostics::framework_diagnostics,
            llama_process::server_start,
            llama_process::server_stop,
            llama_process::server_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running llamaUI");
}
