# Phase 2 — Qt Foundation Status

## Status

Started and functional.

## Files added

- `qt_app/main.py`
- `qt_app/app/application.py`
- `qt_app/app/main_window.py`
- `qt_app/app/theme.py`
- `qt_app/app/pages/base.py`
- `qt_app/app/pages/placeholders.py`
- `qt_app/app/widgets/buttons.py`
- `qt_app/app/widgets/cards.py`
- `qt_app/app/widgets/header.py`
- `qt_app/app/widgets/inspector.py`
- `qt_app/app/widgets/sidebar.py`
- `qt_app/app/services/diagnostics.py`
- `qt_app/app/services/dialogs.py`
- `qt_app/app/services/llama_server.py`
- `qt_app/llama_data/paths.py`
- `qt_app/llama_data/storage.py`
- `qt_app/llama_data/llama_options.py`
- `qt_app/llama_data/models.py`
- `qt_app/llama_data/stores.py`
- `qt_app/tests/smoke_services.py`

## Implemented

- Native Qt application bootstrap using PySide6.
- Dense dark shell with sidebar, center stack, right inspector.
- Placeholder pages for Library, Discover, Run, Profiles, Settings, Diagnostics.
- Run page shell showing the required main controls and advanced group structure.
- Versioned JSON persistence helpers with atomic writes.
- Core models for app config, HF token source, local models, and per-model profiles.
- Stores for config, library, and profiles.
- Curated llama option catalog foundation.
- Framework diagnostics service for Qt/session/GPU/portal evidence.
- Native dialog helper module.
- llama-server binary validation/introspection service.

## Verification observed

Native Qt shell smoke:

```text
platform= wayland
visible= True
rc= 0
```

Data/services smoke:

```text
pass framework diagnostics type
pass gpu vendor enum
pass Qt Wayland plugin discoverable
pass llama probe type
pass missing binary rejected
pass config round trip
pass library round trip
pass profile round trip
```

Static Python compile:

```text
python -m compileall -q qt_app
```

completed with no output/errors.

## Notes

- Tauri product work is stopped. Old Tauri files remain as reference only.
- Some parallel subagents failed after landing partial files; stale package exports and unused stubs were reconciled manually.
- `qt_app/app/shell.py` and unused service stub files were removed after the working `main_window.py` path passed smoke.

## Next phase

Phase 3: dynamic llama-server introspection.

- Use selected binary from Settings.
- Parse `--help` into supported options.
- Merge parsed flags with curated metadata.
- Persist schema by binary path/version/hash.
- Show unsupported/unknown options clearly in Diagnostics and Run settings.
