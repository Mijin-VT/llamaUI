# Phase 12 — Six fixes (1-5 + 7)

This phase addresses five user-reported issues plus a UI redesign of
the arguments page. Each item lists (a) the user-visible problem,
(b) the root cause in current code, (c) the smallest set of changes
that fixes it, (d) acceptance criteria I will verify before yielding.

Issue 6 was fixed by the user; we are not touching it. Issue 7
adds search, filter, and multi-column layout to the arguments page
plus a red "user changed" indicator.

Order of work: 0 first (data shape is a hard prerequisite for 4/5),
then 1, then 4, then 5, then 2, then 3, then 7.

---

## 0. `LocalModel.mmproj_path` exists and is populated

### Why this is first
Issues 4 and 5 both depend on the app knowing which companion files
(multimodal projectors, encoders, etc.) live alongside a model. The
catalog filter in `library_scan.py` already separates primary
from companion (`is_companion_gguf` returns True for mmproj-*/text-encoder-*/vision-encoder-*/embedding-*),
but the **app** code does not yet use this knowledge.

### Current state
- `qt_app/llama_data/models.py:LocalModel` has a `companion_paths: list[str]`
  field, populated by `library_scan.scan_library` when it finds files in
  the same directory that match `is_companion_gguf`.
- `LocalModel` is also missing a `mmproj_path: Optional[str]` convenience
  field — the code currently has to filter `companion_paths` for
  `mmproj-` prefixes every time.
- The Run page has no logic that auto-populates the `--mmproj` field
  from the selected model's `mmproj_path`.
- Issue 4 (dropdowns show mmproj files as models) is fixed by
  `_is_primary_runnable_gguf` from Phase 11 §7a, but the user's
  library.json on disk was built before that fix. A library
  rescan on next launch picks up the new filter.

### Change
In `qt_app/llama_data/models.py`:
- Add `mmproj_path: Optional[str] = None` to `LocalModel`.
- In `from_json`, set `mmproj_path` to the first entry of
  `companion_paths` whose basename starts with `mmproj-` (case-insensitive).
  If none, leave None.
- In `to_json`, write the field if non-None (for round-trip clarity).

In `qt_app/app/services/library_scan.py`:
- When `_build_local_model` constructs the `LocalModel`, compute
  `mmproj_path` similarly: first mmproj-*-prefixed file in the same dir,
  else None.

### Acceptance
- A new scan of a directory containing `model.Q4.gguf` and
  `mmproj-model.fp16.gguf` produces a `LocalModel` with
  `companion_paths=[".../mmproj-model.fp16.gguf"]` and
  `mmproj_path=".../mmproj-model.fp16.gguf"`.
- A new scan of a directory containing only the model (no companion)
  produces `mmproj_path=None`.
- Smoke assertion in `smoke_services.py` for each case.

---

## 1. Add "Enable reasoning" toggle to the catalog

### Current state
The catalog has `reasoning_budget` (INTEGER, default -1) but no
on/off toggle for thinking. The Qwen3 reasoning models expose this
as the `-rea, --reasoning [on|off|auto]` flag in `llama-server --help`.

### Change
In `qt_app/llama_data/llama_options.py`:
- Add `_opt("reasoning", "--reasoning", OptionKind.STRING, "Server /
  API", "Enable reasoning", "Whether the model uses its reasoning /
  thinking trace: on, off, or auto. Recommended 'on' for Qwen3
  reasoning models.", default=LlamaOptionValue.from_raw(OptionKind.STRING,
  "auto"), restart_required=False, importance=1, enum_values=(("on","on"),
  ("off","off"), ("auto","auto")))`.
- Add `reasoning` to `MAIN_OPTION_IDS` in `qt_app/app/pages/run.py`.

The dropdown is rendered automatically because the option has
`enum_values` non-empty (Section 4b). The form will show
`Enable reasoning: [on ▾]` next to `Reasoning budget` in the main
settings card.

### Acceptance
- Re-launch the app: Main settings now shows **Enable reasoning**
  dropdown and **Reasoning budget** number field side-by-side.
- Setting `Enable reasoning=on` and `Reasoning budget=2048` produces
  `--reasoning on --reasoning-budget 2048` in argv.
- Setting `Enable reasoning=off` and `Reasoning budget=2048`
  produces `--reasoning off --reasoning-budget 2048`.
- Leaving both at default (auto/-1) produces no flags.
- Smoke assertion in a new `smoke_section12.py`.

---

## 2. Log viewer scroll-to-bottom on append

### Current state
`qt_app/app/pages/run.py` log lines land in the `QPlainTextEdit`
(`self.logs`) and re-scroll to the top on every update because the
widget cursor is at position 0 by default.

### Change
In the same file, find the slot that re-renders the log buffer
(likely a `QTimer.singleShot` drain) and at the end of that drain,
move the cursor to the end:
```python
cursor = self.logs.textCursor()
cursor.movePosition(QTextCursor.End)
self.logs.setTextCursor(cursor)
```

Standard chat-app follow-tail behavior: the cursor always sits at
the bottom. Manual scroll-up still works while no new lines arrive;
the next appended line will yank back to the bottom.

### Acceptance
- During a long-running model load (or any time many log lines are
  produced in quick succession), the log viewer always shows the
  most recent line. The scrollbar thumb sits at the bottom.
- The user can scroll up to read older lines; new lines still
  follow the cursor to the end (chat-app follow-tail).

---

## 3. "Save" vs "Save As" semantics

### Current state
`qt_app/app/pages/run.py` has `Save Profile` and `Save As` buttons.
The user says both behave the same (the same dialog / no dialog). The
desired behavior:
- **Save**: overwrites the currently-selected profile for this model.
  If no profile is selected, the default profile for the model is
  overwritten (i.e. created if missing). If a profile is selected, the
  settings go into that profile.
- **Save As**: always shows a Name dialog; creates a new profile with
  the entered name (or, if the name already exists, prompts before
  overwriting).

### Change
In `qt_app/app/pages/run.py`:
- Add a new method `_save_profile` that:
  - If `self._selected_profile()` is not None and the model_id matches:
    write settings/user_set/raw_args into that profile and `upsert`.
  - If `self._selected_profile()` is not None but model_id mismatches:
    log a status message and call `_save_profile_as` instead.
  - If no profile is selected: create a default profile (name
    `"Default"`, `is_default=True`) for the current model, upsert it,
    and reload profiles. This is the "Save" case the user is asking
    for: saves the default profile for the current model.
- The existing `Save As` button:
  - Build a name suggestion from the model filename (`Qwen3.6-27B-Q4_K_M → "Qwen3.6-27B (Q4_K_M)"`).
  - Open a `QInputDialog.getText(self, "Save profile as", "Profile name:",
    text=name_suggestion)` (with QInputDialog's standard cancel button).
  - If user cancels, return.
  - If name is empty, return with a status message.
  - If a profile with that name already exists, ask
    `QMessageBox.question(Yes|No)` to confirm overwrite. If No, return.
  - Create the new `ModelProfile(id=uuid4(), model_id=model.id, name=name, ...)`
    with the current settings/user_set/raw_args, `upsert`, and reload
    the profile combo so the new profile is now selected.

### Acceptance
- With a model selected and no profile selected, clicking **Save**
  creates a profile called "Default" for that model and marks it as
  the model default.
- With a profile selected, clicking **Save** updates that profile in
  place; the same name remains selected.
- Clicking **Save As** always opens a name dialog. Cancel aborts.
  Empty name aborts. Duplicate name asks before overwriting.
- Smoke assertion in a new `smoke_section12.py` covering the three
  cases (no-profile-save, save-into-existing, save-as).

---

## 4. Dropdowns show only primary GGUFs (companion files filtered)

### Why this still happens
The library filter from Phase 11 §7a (`_is_primary_runnable_gguf`) is
correct, but the user's library.json on disk was built before that
fix. The dropdowns therefore show stale mmproj files.

### Change
- On the next `app.application.create_app` startup, force a
  rescan of the models directory. The simplest way: in
  `MainWindow.__init__`, if a `LibraryStore` has any `LocalModel`
  whose `path` matches `is_companion_gguf`, drop them and re-scan.
  This is a one-time cleanup of stale data.
- The Run, Library, and Profiles pages already use
  `library_store.list_for_model(...)` which returns the cleaned set.
  No UI change required once the data is clean.
- Additionally, the `model_combo` (Run page) and `model_picker`
  (Library, Profiles) should:
  - show items in format `name · quant · size · provider` (already
    done in Section 7b/7c/7d),
  - sort by model name,
  - group companions under the parent model in the Library detail
    panel (so the user can see the mmproj file exists for the
    selected model).

### Acceptance
- After a re-scan, no mmproj file appears in the Library, Profiles,
  or Run dropdowns. The companion file is still shown in the Library
  detail panel for the model that owns it.
- The mmproj-only models are dropped from the library entirely (the
  scan filter already does this, so the cleanup is just to re-run
  the scan).

---

## 5. Auto-populate `--mmproj` from the selected model's companion

### Current state
The catalog has `mmproj` (STRING, default None) as a free-form path
field. The user has to type it in. The selected model already knows
its mmproj path (after fix 0).

### Change
In `qt_app/app/pages/run.py`:
- When the model selection changes, look up the selected
  `LocalModel.mmproj_path`. If it exists:
  - Set the `mmproj` editor's text to that path.
  - Add `mmproj` to the profile's `user_set` (so the value is
    emitted by `build_argv`).
  - Show a small status message like `Auto-detected mmproj:
    <basename>`.
- If the model has no mmproj companion, clear the `mmproj` editor
  and remove `mmproj` from `user_set`.
- Also: if the user types a path that doesn't exist on disk, show a
  red error label next to the field (use the existing `FieldTile`
  warning style or a new error style) instead of letting the server
  fail later.

### Acceptance
- Selecting a model that has `mmproj-*.gguf` in the same folder
  auto-fills the `mmproj` field with the full path.
- Selecting a model without a companion clears the field.
- Typing a non-existent path shows a "file not found" warning
  inline; the command preview also shows the warning.
- Live test: start the server with the auto-filled mmproj and
  confirm the binary loads the multimodal projector (no
  "failed to open GGUF file" error).

---

## 6. (User-fixed)

(Issue 6 — the missing-mmproj crash — was fixed by the user; we
are not touching it.)

---

## 7. Run-page arguments: search, filter, multi-column layout

### Current state
The Run page renders every option (main + every advanced group) as
a single 2-column `QGridLayout` of label/widget pairs. The page
is a long vertical list. The user has no way to:
  - search for an option by name or flag,
  - see at a glance which options differ from the catalog default,
  - use a multi-column layout when there is enough horizontal
    space.

### Change
In `qt_app/app/pages/run.py` and `qt_app/app/widgets/`:

#### 7a. Search box
At the top of the Advanced-groups card, add a `QLineEdit` with
`setPlaceholderText("Search arguments…")` and `setClearButtonEnabled(True)`.
Connect `textChanged` to a method that re-renders the advanced
groups: for each option, hide its row when neither label, flag, nor
group contains the search substring (case-insensitive). When the
search is empty, all rows are visible again. The main settings
tile grid is unaffected (the user has only ~15 main options, search
is not useful there).

#### 7b. Filter pill: only user-changed
Next to the search box, add a `FilterPill` ("Only changed") with
toggle behaviour. When ON: for each option row, hide it unless the
option's id is in `self._selected_profile().user_set` (or in the
form's locally-tracked `user_set` from `_settings_from_form` when
no profile is selected). The state of this filter is transient
(not persisted).

#### 7c. Multi-column layout
Replace the per-group `QGridLayout` (label/widget) with a flow
layout that wraps to N columns based on the available width.
Implementation:
  - For each group, build a `QWidget` that hosts a custom layout
    `FlowLayout` (PySide6 ships one in Qt's example set, but
    includes a 30-line implementation; if not available, add a
    small `FlowLayout` in `qt_app/app/widgets/flow.py`).
  - Each option renders as a single `OptionCard` widget (already
    partially in `widgets/cards.py:FieldTile`-style): a vertical
    card with the option label at the top, flag in muted text,
    editor below, and a small red dot in the top-right corner when
    `option_id in user_set`.
  - `FlowLayout` re-orders cards into 2-3 columns based on the
    width: target card width is 320 px, so a 720 px group area
    fits 2 columns and a 1080 px area fits 3.

#### 7d. "Changed" red dot
Reuse the `FlowLayout`/`OptionCard` change above. Each card shows
a 6 px red dot in the top-right corner when `option_id` is in the
form's `user_set`. The dot disappears on Reset to defaults.
This is the at-a-glance signal the user asked for.

### Acceptance
- Open Run page → Advanced groups card has a search box, a "Only
  changed" filter pill, and a multi-column flow layout of options.
- Type "kv" in the search box → only KV-cache options visible
  (`cache_type_k`, `cache_type_v`, `defrag_thold`, `flash_attn`,
  etc.); everything else hidden.
- Click "Only changed" pill → empty form shows zero cards.
  Set `ctx_size=8192` → only the `Context size` card is visible
  (and has a red dot in its top-right).
- Resize the window wider → the flow layout grows from 2 columns
  to 3 when the group area reaches ~1080 px wide.
- Reset to defaults → all cards become visible again and the red
  dot disappears.
- Smoke assertion in `smoke_section12.py`: a synthetic 6-option
  group renders as 2 cards in a 720 px area, 3 cards in a 1080 px
  area.

---

## Verification plan

After all six changes:

```bash
python -m compileall -q qt_app
python qt_app/tests/smoke_services.py
for s in 0 1 3 4 5 6 7 10 11 12; do
    python qt_app/tests/smoke_section$s.py
done
```

New `smoke_section12.py` covers fixes 0, 1, 3, 5, 7:
- mmproj detection from a synthetic models dir.
- `--reasoning on` lands in argv when set.
- Save As shows a QInputDialog; smoke can simulate by calling
  `_save_profile_as_with_name("Qwen3.6")` directly.
- `--mmproj` auto-fills when selecting a model with companion.
- `FlowLayout` packs 6 cards into 2 columns at 720 px, 3 columns
  at 1080 px.
- `FilterPill` "Only changed" hides cards whose id is not in
  `user_set`.

Live launch + final argv inspection with the real Qwen3 model
and the real mmproj in the same folder.

---

## Order of execution

1. **Issue 0** — `LocalModel.mmproj_path` field + scan populates it.
2. **Issue 1** — catalog `reasoning` option + MAIN_OPTION_IDS.
3. **Issue 4** — one-time cleanup of stale library data on startup.
4. **Issue 5** — auto-populate `--mmproj` in `_on_model_changed`.
5. **Issue 2** — log viewer scroll-to-bottom.
6. **Issue 3** — Save vs Save As semantics.
7. **Issue 7** — `FlowLayout` widget + `OptionCard` widget in
   `qt_app/app/widgets/`, refactor the Run page's advanced-groups
   card to use them, add the search box, "Only changed" filter
   pill, and red-dot indicator.
8. Verify: full smoke bundle, live launch, screenshot pass.

(Steps 1-6 are interleaved with 7 because the Run page's flow
layout lives in the same file as the changes for 2/3/5. The order
is chosen so each step lands on a stable base.)

---

## Risks / non-goals

- I do not change the Library/Run/Profiles page structure beyond
  Issue 4's data cleanup. The fix is data-level (stale data
  cleanup) plus an auto-fill behavior on the Run page.
- I do not change the model-card or sidebar.
- I do not change the runtime controller.
- The companion-detection regex already covers mmproj-*, but if the
  user has an unusual file (e.g. a Qwen `merger` or `tokenizer.model`
  GGUF), the existing filter is the contract: it is what the user
  sees in dropdowns. If they want a new pattern, they tell me.
- Issue 7's `FlowLayout` does not affect the main settings card
  (it stays in the 2-column `QGridLayout` for visual density). The
  flow layout is only for the advanced groups card.
