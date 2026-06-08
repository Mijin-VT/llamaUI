use crate::types::{FrameworkDiagnostics, GpuVendor, WorkaroundInputs};
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

pub struct WorkaroundState(pub Mutex<WorkaroundInputs>);

fn env_var(name: &str) -> Option<String> {
    std::env::var(name).ok().filter(|v| !v.is_empty())
}

fn read_trimmed(path: impl AsRef<Path>) -> Option<String> {
    std::fs::read_to_string(path).ok().map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

fn portal_descriptors() -> Vec<String> {
    let dir = Path::new("/usr/share/xdg-desktop-portal/portals");
    std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .filter_map(|entry| entry.file_name().into_string().ok())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

fn detect_gpu_vendor() -> GpuVendor {
    let Ok(entries) = std::fs::read_dir("/sys/class/drm") else {
        return GpuVendor::Unknown;
    };

    let mut found_amd = false;
    let mut found_intel = false;
    for entry in entries.filter_map(Result::ok) {
        let vendor_path = entry.path().join("device/vendor");
        let Some(vendor) = read_trimmed(vendor_path) else {
            continue;
        };
        match vendor.as_str() {
            "0x10de" => return GpuVendor::Nvidia,
            "0x1002" | "0x1022" => found_amd = true,
            "0x8086" => found_intel = true,
            _ => {}
        }
    }

    if found_amd {
        GpuVendor::Amd
    } else if found_intel {
        GpuVendor::Intel
    } else {
        GpuVendor::Unknown
    }
}

fn portal_dbus_reachable() -> bool {
    let Ok(mut child) = Command::new("dbus-send")
        .args([
            "--session",
            "--print-reply",
            "--dest=org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.DBus.Peer.Ping",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    else {
        return false;
    };

    for _ in 0..10 {
        if let Ok(Some(status)) = child.try_wait() {
            return status.success();
        }
        std::thread::sleep(Duration::from_millis(50));
    }

    let _ = child.kill();
    let _ = child.wait();
    false
}

fn active_portal_name(descriptors: &[String], desktop: Option<&str>) -> Option<String> {
    let desktop = desktop.unwrap_or_default().to_lowercase();
    if desktop.contains("kde") && descriptors.iter().any(|d| d == "kde.portal") {
        return Some("kde.portal".to_string());
    }
    if desktop.contains("gnome") && descriptors.iter().any(|d| d == "gnome.portal") {
        return Some("gnome.portal".to_string());
    }
    descriptors.iter().find(|d| d.ends_with(".portal")).cloned()
}

#[tauri::command]
pub fn framework_diagnostics(
    workaround_state: tauri::State<'_, WorkaroundState>,
) -> Result<FrameworkDiagnostics, String> {
    let xdg_session_type = env_var("XDG_SESSION_TYPE");
    let xdg_current_desktop = env_var("XDG_CURRENT_DESKTOP");
    let desktop_session = env_var("DESKTOP_SESSION");
    let gdk_backend = env_var("GDK_BACKEND");
    let wayland_display = env_var("WAYLAND_DISPLAY");
    let display = env_var("DISPLAY");
    let qt_qpa_platform = env_var("QT_QPA_PLATFORM");
    let descriptors = portal_descriptors();
    let nvidia_driver_present = Path::new("/proc/driver/nvidia/version").exists();
    let explicit_sync_disabled = env_var("__NV_DISABLE_EXPLICIT_SYNC").is_some();
    let workaround_inputs = workaround_state.0.lock().map_err(|e| e.to_string())?.clone();
    let active_portal_name = active_portal_name(&descriptors, xdg_current_desktop.as_deref());

    Ok(FrameworkDiagnostics {
        framework: "tauri-webkitgtk".to_string(),
        dialog_backend: "xdg-portal".to_string(),
        xdg_session_type,
        xdg_current_desktop,
        desktop_session,
        gdk_backend,
        wayland_display,
        display,
        qt_qpa_platform,
        portal_descriptors: descriptors,
        active_portal_name,
        portal_dbus_reachable: portal_dbus_reachable(),
        gpu_vendor: detect_gpu_vendor(),
        gpu_driver_version: read_trimmed("/proc/driver/nvidia/version"),
        nvidia_driver_present,
        explicit_sync_disabled,
        workaround_applied: explicit_sync_disabled && nvidia_driver_present,
        workaround_inputs,
    })
}
