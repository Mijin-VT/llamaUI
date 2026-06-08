# Phase 12 — Review fixes (F12-1..7)

The Phase12Review reviewer flagged 8 findings (7 HIGH, 1 MEDIUM).
All closed.

| ID    | File:line                                     | Fix                                                  |
|-------|-----------------------------------------------|------------------------------------------------------|
| F12-1 | `app/services/library_scan.py:177-184`        | Added `_companions_for_path()` and set `companion_paths` on every model, both new and updated |
| F12-2 | `app/pages/run.py:1061`                       | `_save_profile_as` now prompts `QMessageBox.question(Yes|No)` before overwriting an existing name |
| F12-3 | `app/pages/run.py:918-923`                    | `_reload_models` sorts the list by `m.path.casefold()` |
| F12-4 | `app/main_window.py:1-3`                      | Added `from pathlib import Path` to the imports |
| F12-5 | `app/pages/profiles.py:580-587`               | New `_format_model_for_picker()` helper; picker uses `name · quant · size · provider` and sorts by `m.path.casefold()` |
| F12-6 | `app/pages/library.py:464-470`                | `_on_picker_changed` reads `self._picker_models` (set by `_render_picker`) instead of `self._all_models` |
| F12-7 | `app/pages/run.py:562-565`                    | Lifted `setMaxLength` from 64 to 1024 for catalog and schema QLineEdits so long file paths survive |

The smoke 3 assertion was updated from `maxLength == 64` to
`maxLength == 1024` to match the new cap.

After all fixes:

- `python -m compileall -q qt_app` passes.
- `python qt_app/tests/smoke_services.py` 40+ checks pass (the
  8 new mmproj-path tests + 32 pre-existing).
- `python qt_app/tests/smoke_section{0,1,3,4,5,6,7,10,11,12}.py`
  all pass.
- Live: a 109-char mmproj path is preserved through the editor
  and lands in argv verbatim.
