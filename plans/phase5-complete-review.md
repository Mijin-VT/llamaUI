# Phase 5 Complete Review

## Status

Phase 5 is complete after review fixes.

## Implemented

- Settings page persists selected `llama-server`, models directory, host/port, and HF token source through `ConfigStore`.
- HF token Save button persists immediately; Clear persists immediately.
- Profiles page supports real profile persistence through `ProfileStore`.
- Catalog-driven profile detail/editor exists for saved llama.cpp arguments.
- Preset support exists:
  - Conservative CPU
  - Balanced GPU
  - Low Memory
- Reset clears selected profile settings/raw args/preset origin.
- Duplicate creates a new profile with copied settings.
- Set Default enforces one default profile per model.

## Review findings fixed

- Store-level default invariant added/fixed: `ProfileStore.set_default(profile_id)` only demotes defaults for the same `model_id`.
- `SettingValueMap.copy()` added.
- Duplicate profile now uses `profile.settings.copy()`.
- Real settings editor/preset/reset/default actions replace the prior placeholder detail panel.

## Verification

```text
python -m compileall -q qt_app
```

passed.

```text
python qt_app/tests/smoke_services.py
```

passed all 8 smoke checks.

```text
profile_invariant_smoke=ok
```

verified default mutual exclusion per model and SettingValueMap copy semantics.

Qt shell smoke:

```text
platform= wayland
visible= True
rc= 0
```
