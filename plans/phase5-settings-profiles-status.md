# Phase 5 — Settings/Profile Editor Status

## Status

Settings persistence and basic profile creation/duplication are implemented and smoke-tested.

## Files updated

- `qt_app/app/pages/settings.py`
- `qt_app/app/pages/profiles.py`

## Implemented

### Settings

- Loads `AppConfig` through `ConfigStore.default()`.
- Persists selected `llama-server` path.
- Persists models directory.
- Persists host and port defaults.
- HuggingFace token Save button persists token immediately through `HfTokenSource(kind="saved")`.
- Clear token persists `HfTokenSource(kind="none")`.
- Keeps binary validation/introspection flow.

### Profiles

- Profiles page reads `ProfileStore` and `LibraryStore`.
- Added basic real profile creation form: model id/path + profile name + Save Profile.
- Save Profile writes a `ModelProfile` through `ProfileStore.upsert()`.
- Added Duplicate Selected Profile action that copies the selected profile into a new user profile.
- Profile list/details refresh after save/duplicate.

## Verification observed

Static compile:

```text
python -m compileall -q qt_app
```

Service smoke:

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

Settings/profile storage smoke:

```text
settings_profile_smoke=ok
```

Qt shell smoke:

```text
platform= wayland
visible= True
rc= 0
```

## Notes

- A settings subagent completed late and rewrote `settings.py`; smokes were re-run after that final state.
- Full catalog-derived settings controls, reset/preset flows, and per-model default profile selection still need the remaining Phase 5/Run editor pass.

## Next phase

Continue Phase 5/6 boundary:

- Build actual setting controls from runtime schema/catalog.
- Implement Reset and Apply Preset.
- Persist selected model/profile state.
- Then implement real HuggingFace search/download service in Phase 6.
