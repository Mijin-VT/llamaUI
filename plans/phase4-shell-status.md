# Phase 4 — Qt Frontend Shell Status

## Status

Real page scaffolds implemented and smoke-tested.

## Files added/updated

- `qt_app/app/pages/library.py`
- `qt_app/app/pages/discover.py`
- `qt_app/app/pages/profiles.py`
- `qt_app/app/pages/run.py`
- `qt_app/app/pages/settings.py`
- `qt_app/app/pages/diagnostics.py`
- `qt_app/app/main_window.py`
- `qt_app/app/services/hugging_face.py`
- `qt_app/app/services/__init__.py`

## Implemented

- Library page reads `LibraryStore` and `ProfileStore`; shows empty state or local model rows/profile counts.
- Discover page owns a dense search/filter/results/download-queue layout; it uses an honest not-implemented HF service rather than fake results.
- Profiles page reads `ProfileStore` and model metadata; shows empty state or profile rows/details.
- Run page derives visible settings/groups from the curated llama option catalog rather than only hardcoded mock text.
- Settings page validates/parses selected `llama-server` and shows parsed/curated/unknown option counts.
- Diagnostics page shows Qt/session/GPU/portal evidence.
- Main window now uses real page classes instead of generic placeholders for the core routes.

## Verification observed

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

Qt shell smoke:

```text
platform= wayland
visible= True
rc= 0
```

Static compile:

```text
python -m compileall -q qt_app
```

completed with no output/errors.

## Notes

- Parallel page agents wrote partial files late; imports and service exports were reconciled manually.
- Placeholder behavior remains only where later phases own the actual feature implementation: HF network search/downloads, full settings editor, and runtime process control.
- No fake HF results are shown.

## Next phase

Phase 5: Settings/profile editor rewrite.

- Persist selected llama-server path from Settings.
- Build actual setting controls from runtime schema/catalog.
- Implement Save Profile / Save As / Duplicate / Reset / Preset flows.
- Auto-load last/default profile per model.
