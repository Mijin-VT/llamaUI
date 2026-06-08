# Framework Decision — Phase 1

## Decision

Replace Tauri. Use Qt on Python first, specifically PyQt6/PySide6, unless implementation uncovers a hard blocker.

## Reason

The product requirement is native KDE Wayland + NVIDIA without compromises. Tauri/WebKitGTK on this host requires an explicit-sync workaround to avoid a Wayland protocol crash. That violates the requirement.

## Evidence observed

### Environment

- `XDG_SESSION_TYPE=wayland`
- `XDG_CURRENT_DESKTOP=KDE`
- `DESKTOP_SESSION=plasma`
- `WAYLAND_DISPLAY=wayland-0`
- `GDK_BACKEND` unset
- KDE portal descriptor exists at `/usr/share/xdg-desktop-portal/portals/kde.portal`

### Tauri

Normal Tauri launch with the app workaround can keep `target/debug/llama-ui-app` alive, but the workaround is required.

When launched with the app unable to apply the workaround because `__NV_DISABLE_EXPLICIT_SYNC=0` is already set, Tauri/WebKitGTK crashes:

```text
Gdk-Message: Error 71 (Protocol error) dispatching to Wayland display.
```

This reproduces the known Wayland/NVIDIA/WebKitGTK failure mode and proves Tauri does not satisfy the no-compromise framework gate on this machine.

### Qt/PyQt6

Both PyQt6 and PySide6 are importable in the local environment.

Qt platform plugins include native Wayland:

```text
/usr/lib64/qt6/plugins/platforms/libqwayland.so
```

A minimal PyQt6 window ran on native Wayland and exited cleanly:

```text
platform= wayland
visible= True
rc= 0
```

## Consequence

Stop investing in the Tauri frontend. Preserve useful backend/domain logic only conceptually or by porting. Build the product as a native Qt desktop app.

## Recommended stack

- Python 3
- PySide6 preferred for LGPL friendliness, PyQt6 acceptable locally because installed and smoke-tested
- Qt Widgets for fast dense native desktop UI
- Optional QML later only if custom animated UI becomes necessary
- `httpx` or `requests` for HuggingFace and llama-server API
- `aiohttp`/`qasync` or worker threads for async tasks
- `subprocess`/`QProcess` for local llama-server lifecycle and logs
- SQLite or JSON config files for profiles/model metadata

## Immediate next implementation direction

1. Create a new native Qt app skeleton under a separate path, e.g. `qt_app/`, without deleting the old Tauri app yet.
2. Implement the product shell first: sidebar, Library, Discover, Run, Profiles, Settings, Diagnostics.
3. Implement Settings binary selection and native QFileDialog.
4. Implement llama-server introspection from the selected binary.
5. Implement per-model profile schema and Run settings UI.

## Remaining risk

Need package decision later: system Python + dependencies for development; bundled installer/AppImage/Flatpak later.
