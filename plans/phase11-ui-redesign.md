# Phase 11 — UI redesign

This plan addresses 11 user-reported issues, in a single coherent redesign.
Each item lists: (a) the user-visible problem, (b) the root cause in current
code, (c) the smallest set of changes that fixes it, (d) acceptance
criteria I will verify before yielding.

The plan is organized top-down: a small structural change first (shell +
responsive layout) that fixes several issues at once, then per-page work.

---

## 0. Global: responsive shell, dynamic width

Issues addressed: **#2, #10**.

### Current state

`qt_app/app/main_window.py:67-68` uses a horizontal split
`sidebar | (header + stack) | inspector` with three fixed-width widgets:

- `qt_app/app/widgets/sidebar.py:51` — `setFixedWidth(theme.SIDEBAR_WIDTH=220)`
- `qt_app/app/widgets/inspector.py:18` — `setFixedWidth(theme.INSPECTOR_WIDTH=320)`

When the window is smaller than `220 + 320 + stack_min`, the stack
clips or is pushed off-screen — that's the "hidden behind RUN panel" /
"half hidden when window is small" behavior. The shell also uses a
`QStackedWidget` with a single page, so there is no "auto-reorganize
per page" — pages can't opt out of the inspector.

### Change

In `qt_app/app/main_window.py`:

- Replace the fixed `addWidget(inspector)` with a
  `QSplitter(Qt.Horizontal, root)` whose children are
  `[sidebar, center, inspector]`.
- Sidebar and inspector get `setMinimumWidth(160)` /
  `setMinimumWidth(220)` (no `setFixedWidth`). Default splitter sizes
  `[220, 760, 320]`, saved to `QSettings` on close, restored on open.
- Add a collapse button on the inspector's title bar that hides it to
  zero width and shows a small "▸ Inspector" pill on the right edge to
  re-open.
- Add a `QStackedWidget` for the page body is unchanged but a
  per-page `policy` enum (`PagePolicy` in `pages/base.py`) tells the
  shell which side panels to show:
  - `PagePolicy.standard` (Library, Discover, Run, Profiles) — all
    three columns.
  - `PagePolicy.inspector_optional` (Settings) — inspector collapsed
    by default.
  - `PagePolicy.full_width` (Diagnostics) — inspector hidden.

`MainWindow.navigate()` will call `splitter.setSizes(policy_sizes)`.

### Acceptance

- Resize window to 900×720: stack area stays ≥ 520 px, sidebar stays
  ≥ 160 px, inspector is collapsed to 0 px on demand, all controls
  reachable.
- Drag the splitter, close, reopen → sizes restored.
- Diagnostics page shows full width with inspector hidden.

---

## 1. Issue #1 — downloads don't block the UI thread

### Current state

`qt_app/app/pages/discover.py` has 3 workers, all wired with
`thread.started.connect(lambda: worker.run(), Qt.ConnectionType.QueuedConnection)`
and `worker.finished.connect(self._…, Qt.ConnectionType.QueuedConnection)`.
The user reports UI still freezes between the button click and the
first progress tick.

### Root cause

The `DownloadService.download(...)` call ends up in
`download_file(...)` (`qt_app/app/services/download_service.py:82`),
which is **fully synchronous** and streams chunks in 64 KiB reads. The
worker runs on a `QThread` so the streaming itself is off the GUI
thread. The freeze between click and first tick is therefore either:

1. The `huggingface.co` API call for the tree (during `_build_selectable`
   or anywhere `_select_repo` does tree-fetching) runs on the GUI
   thread before the worker is started, **or**
2. The "first chunk" of a 60+ MB repo metadata file is large enough
   that the progress signal fires only after the first ~100 ms, and
   the GUI is briefly unresponsive due to a `getattr`/`is_relative_to`
   or other CPU work in the synchronous setup path of
   `_download_selected`.

I will not know which is the cause without instrumentation, so the
fix is to **remove all sync I/O from the GUI thread** for the
download path:

### Change

In `qt_app/app/pages/discover.py`:

- In `_select_repo()` (which currently calls `_build_selectable`),
  move tree-size hydration to the existing `_CardWorker` path: send
  `(repo_id, file_metadata)` to a `_TreeWorker` that runs
  `urllib.request.urlopen` for the tree on a `QThread`. Show
  `Loading files…` in the file combo while it runs.
- In `_download_selected()`, the only sync work in the call path is
  the `Path(dest_dir).mkdir(...)` and `LibraryStore.default()`. Both
  are cheap, but the **path expansion** (`Path(config.models_dir).expanduser()`)
  reads from disk synchronously. Push the entire download setup
  (config load, dest dir resolution, request build, library registration
  of metadata) into the worker. The worker becomes:
  ```python
  class _DownloadWorker(QObject):
      progress = Signal(str, object)
      finished = Signal(object)
      def run(self):
          try:
              config = ConfigStore.default().load()
              dest_dir = ...
              library = LibraryStore.default()
              ...  # build request, call DownloadService
          except Exception as exc:
              self.finished.emit(("error", str(exc)))
  ```
  The page only needs to: add a `DownloadRow`, set the worker, start
  the thread.
- The progress row must be added **before** the worker emits any
  signal, which is already the case.

### Acceptance

- A live `unsloth/Qwen3-1.7B-GGUF` download with 4 progress callbacks
  shows 4 `DownloadRow` updates while the GUI remains interactive
  (typing in the search box, switching tabs, scrolling the page all
  work between progress ticks).
- A network outage during a download produces a row showing
  `failed: <reason>` and the GUI does not freeze.

---

## 2. Issues #2 + #10 — fixed by Section 0

Covered above. Concrete page-level effects:

- Library / Run / Profiles: 3-column layout that resizes down to
  ~900 px wide.
- Diagnostics: full-width, inspector hidden.
- Profile settings no longer hidden "to the right of the model name"
  (issue #10) because the run/profile body uses a 2-column
  `QFormLayout` with the model-name dropdown on its own row above
  the settings grid (see Issue #11 below).

---

## 3. Issue #3 — small input fields, not 100-char-wide text boxes

### Current state

`qt_app/app/pages/run.py:387-411` `_make_editor` creates
`QSpinBox`/`QDoubleSpinBox`/`QLineEdit` and places them in a
`QGridLayout` with `addWidget(widget, row, 1)`. `QLineEdit` for string
options like `cache_type_k`, `tensor_split`, `split_mode` has no
`setMaxLength` or `setMaximumWidth`, so it stretches to fill the
column (300+ px wide).

### Change

- In `_make_editor`, for `OptionKind.STRING`, create a `QLineEdit`
  with `setMaxLength(64)` and `setMinimumWidth(120)`. For
  `OptionKind.INTEGER`/`FLOAT`, the `QSpinBox` already auto-sizes
  but lacks a `setMinimumWidth(110)` — add it.
- In `_make_schema_editor` (`run.py:413`), apply the same
  `setMaxLength(64)` for `QLineEdit`.
- Add a `QSS` rule in `qt_app/app/theme.py`:
  `QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { max-width: 320px; min-width: 120px; }`
  with the same for the Discover search box and Library filter.
- For the long `extra_args` editor (raw extra args, full command
  line), keep `setMinimumWidth(0)` so it can stretch — it's
  intentionally wide.

### Acceptance

- Open Run page, expand any group: each editor cell is between
  120 px and 320 px wide, regardless of the right-column width.
- A 5-digit number field shows the spinbox sized to its digits, not
  the column.

---

## 4. Issue #4 + #6 — dropdowns for enumerated options, highlight important fields

### Current state

`LlamaOption` (`qt_app/llama_data/llama_options.py:25-36`) has no
concept of "this is an enum". `cache_type_k`, `cache_type_v`,
`split_mode`, `rope_scaling`, `tensor_split` are all rendered as
`QLineEdit` with the default value as a hint text. There's no
styling to differentiate "important" options.

### Change

#### 4a. Extend the catalog

In `qt_app/llama_data/llama_options.py`:

- Add `enum_values: Tuple[Tuple[str, str], ...] = ()` to
  `LlamaOption` (a tuple of `(value, display_label)` pairs; empty
  tuple means free-form string).
- Add `importance: int = 0` (0 = normal, 1 = important, 2 = critical)
  for visual styling.
- Populate `enum_values` for these options:
  - `cache_type_k`/`cache_type_v`:
    `("f16","f16"), ("f32","f32"), ("bf16","bf16"), ("q8_0","q8_0"), ("q4_0","q4_0"), ("q5_0","q5_0"), ("q5_1","q5_1")`
  - `rope_scaling`: `("none","none"), ("linear","linear"), ("yarn","yarn")`
  - `split_mode`: `("none","none"), ("layer","layer"), ("row","row")`
  - `poll`: `("none","none"), ("main","main"), ("all","all"), ("vision","vision")` if present
  - `samplers`: free-form list
- Mark these as `importance=1` (highlighted): `cache_type_k`,
  `cache_type_v`, `n_gpu_layers`, `ctx_size`, `batch_size`,
  `parallel`, `temp`, `top_p`, `top_k`.

#### 4b. Render dropdowns in Run

In `qt_app/app/pages/run.py` `_make_editor`:

- If `option.enum_values` is non-empty, return a `QComboBox` with
  `addItems([label for _, label in enum_values])` and store the
  underlying value in `widget.currentData()`. Add an "(unset)"
  first item with `userData=None` so the user can revert to "no
  override".
- For boolean options, keep `QCheckBox`.
- For numeric, keep `QSpinBox`/`QDoubleSpinBox` with `setMinimumWidth(110)`.
- Free-form `QLineEdit` only for options with empty `enum_values`
  and not a number/bool.

In `_make_schema_editor` (unknown schema options): the dynamic
introspection cannot know enum membership, so default to a
`QLineEdit` with `setPlaceholderText` taken from the schema's
allowed-values hint when present. Add a tooltip with the schema
description.

#### 4c. Highlight important fields (Issue #6)

In `qt_app/app/theme.py`, add QSS rules:

```css
QLabel[important="1"] { color: #f5d76e; font-weight: 600; }
QLabel[important="2"] { color: #ff8a65; font-weight: 600; }
```

In `_option_label`, the label widget gets `setProperty("important",
str(option.importance))` and `style().polish(label)`.

### Acceptance

- Open Run, expand the **Context / KV-cache** group. `KV cache K
  type` and `KV cache V type` are dropdowns with `f16 / bf16 / q8_0
  / q4_0 / q5_0 / q5_1` as choices.
- `RoPE scaling` is a dropdown with `none / linear / yarn`.
- `Split mode` is a dropdown with `none / layer / row`.
- The label of `Context size`, `GPU layers`, `Temperature`, etc. is
  rendered in the highlighted color.
- The command preview reflects the chosen enum value (e.g.
  `--cache-type-k q8_0`).
- A previously-free-form string option without enum values still
  shows a text field.

---

## 5. Issue #5 — dashboard layout, not a flat list

### Current state

`_build_main_settings` (`run.py:232-256`) lays out all 15 main
options in a 2-column `QGridLayout` (label | widget). Advanced
groups use a `QToolBox` with each group as its own page; inside
each page is again a 2-column `QGridLayout` with `addWidget(label,
row, 0) addWidget(widget, row, 1)`. The whole page therefore reads
as a flat list with no visual hierarchy beyond the group headers.

### Change

In `qt_app/app/pages/run.py`:

- Replace the `QToolBox` for advanced groups with a
  `QTreeWidget`-free approach: a vertical stack of
  `CollapsibleGroup` cards, each with a header button (group name +
  item count + small expand/collapse caret). First implementation:
  subclass `QWidget` with a `QLabel` header and a body
  `QWidget` whose `setVisible` is toggled by a click on the header.
  Default: first group (Performance) is expanded; others collapsed.
- Inside each `CollapsibleGroup`, change the 2-column `QGridLayout`
  to a responsive 2-column **dashboard grid**:
  - Sort options by `importance` (descending), then by label.
  - Each option uses a small `OptionCard` (already partially exists
    in `widgets/cards.py` as `FieldTile`): label (with importance
    color), flag in muted text, current value, default in
    parentheses, restart/runtime-change badge, "?" tooltip with the
    help text. Editor widget below the label, not to the right.
  - Use `QGridLayout` with `columnStretch = [3, 1]` (label/description
    column wider than editor column) — current layout uses
    `addWidget(label, row, 0); addWidget(widget, row, 1)` which is
    exactly the wrong ratio for a dashboard.
- In `_build_main_settings`, render the **main** options in a
  horizontal 2-column tile grid (left/right card) so they look like
  a control panel, not a list.

In `qt_app/app/theme.py`, add `CollapsibleGroup` QSS for an
expand/collapse header that looks like a tab strip.

### Acceptance

- Each option renders with: prominent label, subtle flag name,
  current value, default in parentheses, badge for "restart
  required" vs "runtime change", tooltip with help text.
- The main settings tile-grid is visually distinct from the
  advanced groups.
- The KV-cache group, GPU/offload group, etc. are clearly
  separated by visual cards, not just text.
- All groups are collapsed by default except the first; the user
  can expand all from a single button.

---

## 6. Issue #7 — only user-changed args land in the final command

### Current state

`qt_app/app/services/runtime.py:131-174` `build_argv` iterates
**every** value in `profile.settings` and emits its `--flag value`
pair, regardless of whether the user actually changed it. The
catalog defaults like `cache_type_k="f16"`, `split_mode="none"` are
saved into the profile on first edit (because
`_settings_from_form` calls `settings.with_value(option, value)`
unconditionally), and then re-emitted on the command line. This
makes the command much longer than the user asked for, and at
worst, passes flags the binary does not support (causing
`llama-server` to error out).

### Change

#### 6a. Track user-set vs catalog-default in the SettingValueMap

In `qt_app/llama_data/llama_options.py`:

- Add a parallel structure: a second `SettingValueMap`-like
  container called `UserOverrides` that lives on the
  `ModelProfile`. The simplest representation: a
  `user_set: set[str]` (set of `option_id`) on `ModelProfile`. Plus
  a method `is_user_set(option_id) -> bool`.
- `ModelProfile` already exists at `models.py:115`. Add
  `user_set: set[str] = field(default_factory=set)`.

#### 6b. Mark at the editor level

In `qt_app/app/pages/run.py`:

- When the user touches an editor for the first time, add
  `option_id` to `profile.user_set` (in
  `_settings_from_form`/`_load_profile_into_form`).
- A "Reset to defaults" button on the toolbar clears
  `profile.user_set`.

#### 6c. Emit only user-set values

In `qt_app/app/services/runtime.py:131-174` `build_argv`:

- After computing the base `argv = [binary, --model, path, --host,
  --port]`, iterate `profile.settings.items()` but only emit
  `--flag value` when `profile.is_user_set(option_id) AND
  option_id not in {model, host, port}`. This drops the catalog
  defaults from the command line.
- `argv.extend(profile.raw_args)` stays — these are explicit
  user-typed args.

#### 6d. Migration for existing profiles

`ModelProfile.from_json` (`models.py:132`) should accept
`user_set` (default empty set). Add a `v0_to_v1` migration if
needed.

### Acceptance

- Open the Run page on a fresh profile, **without touching any
  field**, and click Start: the command preview shows
  `<llama-server> --model <path> --host 127.0.0.1 --port 8080` and
  nothing else. (Today it shows ~25 flags.)
- Change `Context size` to 8192 and `KV cache K type` to `q8_0`:
  the command preview now contains `--ctx-size 8192
  --cache-type-k q8_0` and no other flags.
- Save the profile, close, reopen, click Reset to defaults:
  command preview returns to the minimal form.

---

## 7. Issues #8, #9, #11 — model dropdown instead of list

### Current state

- Library: `_TableRow` (`library.py:101`) renders one row per
  `LocalModel`; the `_show_detail` panel (`library.py:317`) shows
  the full path + every companion file. The model is selected by
  clicking the row, not from a dropdown.
- Profiles: similar list-by-model approach. Currently lists every
  LocalModel; mmproj files reach this list because
  `_is_primary_runnable_gguf` doesn't filter them.
- Run: `model_combo` already exists at `run.py:174` and lists model
  filenames, but with no separation from companion files in
  storage.

### Change

#### 7a. Filter mmproj / non-primary files in `library_scan.py`

In `qt_app/app/services/library_scan.py:_is_primary_runnable_gguf`:

- Reject `mmproj*.gguf` (case-insensitive, anywhere in the name).
- Reject any `*.gguf` whose name contains `mmproj-` or
  `text-encoder-` or `vision-encoder-` or `tokenizer` or
  `embedding` (these are companion files).
- Keep the existing split-filter (`-00001-of-NNNNN.gguf` is the
  primary; other parts are companions).
- Add `is_primary_gguf` and `is_companion_gguf` helpers so the
  library detail panel can still show companion files for the
  currently selected model, but they don't appear as separate
  "models" in the list.

#### 7b. Library: dropdown + detail

In `qt_app/app/pages/library.py`:

- Replace the `_TableRow`-per-model grid with a `QComboBox` at the
  top: `Model:` `[Qwen3-1.7B-Q4_K_M.gguf ▾]` (showing
  `name · quant · size · provider`).
- Below the dropdown, a single detail card with sections:
  - **Header**: model name + size + quant + fit chip.
  - **HuggingFace** (if `hf_repo`): repo, file, sha, license,
    base model, tags.
  - **Files** (if `companion_paths` non-empty): list of companion
    file paths with "Reveal" buttons.
  - **Profiles** (if any): list of saved profile names, each
    clickable to set as default or to jump to Run page with that
    profile pre-selected.
  - **Actions**: `Run`, `Reveal in file manager`, `Open on
    HuggingFace`, `Create Profile`, `Delete local metadata`.
- The model combo's dropdown list still shows all models (so the
  user can scan), but only one is "open" at a time.

#### 7c. Profiles: dropdown

In `qt_app/app/pages/profiles.py`:

- Replace the "By model" list (which currently shows every
  LocalModel) with a single `QComboBox` at the top:
  `Editing model:` `[Qwen3-1.7B-Q4_K_M.gguf ▾]`.
- Below it, the existing profile list (per model) and editor for
  the selected profile.
- Add a button "Create profile for this model" next to the
  dropdown.

#### 7d. Run: already has a dropdown

`run.py:174` `model_combo` already exists. Just confirm that
mmproj-filtered `LocalModel`s are the only things listed, and
make sure the dropdown's items show
`name · quant · size · provider` in the text (not just the
filename).

### Acceptance

- Drop a `Qwen3.5-Q4_K_M.gguf` and its `mmproj-Qwen3.5-Q4_K_M.gguf`
  into the models directory, scan: only `Qwen3.5-Q4_K_M.gguf`
  appears in the Library and Profiles dropdowns. The companion is
  shown in the detail panel as a file link.
- Open Library: the top of the page is a single dropdown of
  models, not a table. Selecting one shows the detail card.
- Open Profiles: the top of the page is a single dropdown; the
  profile list below is for that one model.
- Open Run: the existing model combo shows only the primary GGUFs.

---

## 8. Cross-cutting: theme / stylesheet update

`qt_app/app/theme.py`:

- Add the input-width cap (Issue #3).
- Add the importance-label colors (Issue #4/6).
- Add the `CollapsibleGroup` header style (Issue #5).
- Add the `DownloadRow` progress bar style (already mostly done
  in `widgets/cards.py`).
- Add a "dashboard card" style for the main settings grid.
- Add a style for the "model dropdown" (`QComboBox#ModelPicker`).

---

## 9. Verification plan

After each change I will run:

```bash
python -m compileall -q qt_app
python qt_app/tests/smoke_services.py
```

And a new targeted smoke that:

1. Constructs `MainWindow` (1 s) and asserts no `addWidget` warnings.
2. Loads a synthetic `LibraryStore` with one primary GGUF + one
   `mmproj` companion + one non-GGUF file: asserts the dropdown
   has exactly 1 entry.
3. Constructs the new `RunPage` and asserts the `_make_editor`
   function returns a `QComboBox` for `cache_type_k` and
   `split_mode`, a `QSpinBox` for `ctx_size`, and a `QLineEdit`
   for `tensor_split`.
4. Constructs a `ModelProfile(user_set={"ctx_size"})` with
   `settings={"ctx_size": 8192, "cache_type_k": "f16"}` and
   asserts `build_argv(...)` emits `--ctx-size 8192` and **no**
   `--cache-type-k` flag.
5. Shrinks the window to 900×720 and asserts the stack is
   visible (no `clip`).

---

## 10. Risks / explicit non-goals

- **No change to the on-disk profile schema** beyond adding the
  optional `user_set` field. Existing profiles default to
  `user_set = empty` which is a breaking behavioural change:
  previously, the saved `cache_type_k="f16"` was re-emitted; now
  it isn't. I will handle this by treating all options that are
  equal to the catalog default as "not user set" on first load —
  i.e. `ModelProfile.from_json` filters out values equal to the
  default and adds the rest to `user_set`. This is a one-time
  migration done in `from_json`.
- **No change to the download chunk size, the `DownloadService`
  API, or the `runtime.py` controller's public surface.** The
  change is purely "shift sync I/O off the GUI thread" and "stop
  emitting default values".
- **No change to the Sidebar navigation or the PageBase API**
  beyond the new `PagePolicy`.
- **No change to the catalog option ids.** Renaming `cache_type_k`
  to anything else would invalidate saved profiles. The fix is
  purely additive (`enum_values`, `importance`).

---

## 11. Out of scope (will not change in this phase)

- The Tauri legacy code (`src-tauri/`, `src/`) is not touched.
- The HF download service's chunk size and retry policy.
- The Diagnostics page's network probes (already working).
- The `ProfileStore` migration chain (already applied).
- The `llama-server` introspection parser.

---

## 12. Order of work

1. **Section 0** (responsive shell + PagePolicy) — small, fixes
   issues #2 and #10 for the entire app at once.
2. **Section 7a** (mmproj filter) — pure backend, one smoke
   test, then move on.
3. **Section 7b, 7c, 7d** (dropdowns in Library, Profiles, Run) —
   dependent on 7a.
4. **Section 4a, 4b, 4c** (enum dropdowns + importance) — touches
   the catalog and the Run editor.
5. **Section 3** (input-width cap) — small, independent of the
   rest.
6. **Section 5** (CollapsibleGroup dashboard layout) — depends on
   4 and 3.
7. **Section 6** (only user-set args) — backend, no UI work
   beyond a "Reset to defaults" button.
8. **Section 1** (downloads off GUI thread) — last, since it
   requires careful instrumentation.
9. Verification bundle: compile, smoke_services, the 5 new
   targeted smokes.

After everything: a real launch and a screenshot of each page to
confirm the layout matches the plan.
