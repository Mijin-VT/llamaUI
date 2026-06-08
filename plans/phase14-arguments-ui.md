# Phase 14 — Arguments UI rework

Three real, repeated complaints. Each is described as the user said
it, in their words, with the concrete fix.

---

## 0. (Pre-plan) QSS parse warning

A pre-existing bug in `qt_app/app/theme.py:281-282` made the global
QSS parse with a warning on every `QApplication.setStyleSheet` call:
the `QPushButton#FilterPill { ... }` rule was missing its closing
`}}` and the next rule's `{ width: 0; }` was silently merged in.
This has already been fixed in this phase. Future regressions in
the QSS should be caught by a smoke that asserts
`setStyleSheet` does not emit a warning (see `smoke_section14`).

---

## 1. "I already showed you. arg 1a means Text+editable field." — Main settings as a 2-column table

### Current state

`_build_main_settings` at `qt_app/app/pages/run.py:271-305` uses a
`QGridLayout` with 2 columns inside a `QGridLayout` (label | widget)
wrapped in a `setMaximumWidth(720)` centering widget. The result is a
single-column vertical list of `[label, editor]` rows (8 rows for 16
options). The user has to scroll inside the card on a 1100 px window.

### Fix

Replace the 2-column label/widget `QGridLayout` with a proper
2-column **table layout**: a `QGridLayout` with **16 cells of 2
columns x 8 rows**, where each cell contains a complete `OptionCard`
(label + editor + flag). The 8 rows and 2 columns are real, not a
flow layout — at any window width the user gets exactly 2 columns
of options, and the user can scan top-to-bottom, left-to-right like
a book.

The centering wrapper goes away. The card now stretches to fill
the body width, with the 2-column table inside.

### Files

- `qt_app/app/pages/run.py:_build_main_settings` (line 271)
- `qt_app/app/widgets/cards.py:OptionCard` (already exists; may
  need a small adjustment for tighter grid packing — minimum width
  280 px is fine)

### Acceptance

- On a 1100 px wide window, the main settings card shows 16
  options arranged in 2 columns of 8 rows. All options are visible
  without scrolling.
- Each cell shows the option label, the editor (combo/spinbox/
  slider), the flag in muted text, and the importance dot.
- The "Apply Preset", "Save", "Save As", "Reset to defaults" toolbar
  row is unchanged and stays above the 2-column table.
- The command preview stays in the same place.

---

## 2. "WHERE THE FUCK ARE MY SLIDERS?" — QSlider with min-max, paired with the spinbox

### Current state

`_make_editor` at `qt_app/app/pages/run.py:526` returns
`QSpinBox` / `QDoubleSpinBox` for numeric options. The user wants
a **horizontal slider with a draggable thumb** alongside the
spinbox — a real `QSlider(Qt.Horizontal)` with `setMinimum` /
`setMaximum` and a draggable handle. The spinbox stays for typing
exact values; the slider is the new drag interaction.

### Fix

New widget `SliderSpinBox` (integer) and `SliderDoubleSpinBox`
(float) in `qt_app/app/widgets/slider_spin.py`:

- `QSlider(Qt.Horizontal)` on the left, takes ~60% of the width.
- `QSpinBox` / `QDoubleSpinBox` on the right, takes ~40% of the
  width.
- They share one value model. Setter to slider or spinbox updates
  the other. `valueChanged` is emitted by the composite widget
  (so the existing `valueChanged.connect(self._on_editor_changed)`
  in `_make_editor` works unchanged).
- `setRange(min, max)`, `setValue(v)`, `setSingleStep(s)`,
  `blockSignals(bool)`, `value()` all match `QSpinBox`'s API.

For each numeric option, set a sensible min/max from the catalog
data:

- `ctx_size` → 256 .. 1_048_576
- `cache_type_k/v` → these are STRING enums, no slider.
- `n_gpu_layers` → 0 .. 999
- `threads` → 0 .. 256
- `batch_size` → 1 .. 8192
- `ubatch_size` → 1 .. 8192
- `parallel` → 1 .. 32
- `temp` → 0.0 .. 2.0
- `top_p` → 0.0 .. 1.0
- `top_k` → 0 .. 200
- `repeat_penalty` → 0.0 .. 2.0
- `defrag_thold` → -1.0 .. 1.0
- `min_p` → 0.0 .. 1.0
- `rope_freq_base` → 0.0 .. 1000000.0
- `rope_freq_scale` → 0.0 .. 100.0
- `seed` → -1 .. 2_147_483_647
- `n-cpu-moe` → 0 .. 256
- `lookahead`, `xtc-probability`, `xtc-threshold` etc. → sensible
  ranges from the binary's `--help` output.

If the catalog has no explicit range, fall back to a wide default
(-1_000_000 .. 1_000_000 for int, -1000.0 .. 1000.0 for float). The
slider is still draggable across the full range; it just feels
smoother with a tight range.

### Files

- `qt_app/app/widgets/slider_spin.py` (new — `SliderSpinBox`,
  `SliderDoubleSpinBox`)
- `qt_app/app/widgets/__init__.py` (export both)
- `qt_app/app/pages/run.py:_make_editor` (line 526) — return
  `SliderSpinBox` / `SliderDoubleSpinBox` instead of
  `QSpinBox` / `QDoubleSpinBox`
- `qt_app/app/pages/run.py:_make_schema_editor` (line 573) — same
  swap for schema options
- `qt_app/llama_data/llama_options.py` — add `min_value` / `max_value`
  / `step` to `LlamaOption` so the ranges are data-driven, not
  hard-coded in the editor factory

### Acceptance

- Every numeric option in the main settings and advanced groups
  has a `SliderSpinBox` / `SliderDoubleSpinBox`.
- The user can drag the slider thumb and the value updates in the
  spinbox; the user can type in the spinbox and the slider thumb
  moves.
- A new `smoke_section14.py`:
  - `_make_editor` for `OptionKind.INTEGER` returns a
    `SliderSpinBox`.
  - Setting `slider.setValue(123)` updates both the slider thumb
    and the spinbox.
  - Setting `spinbox.setValue(456)` updates both.
  - The `valueChanged` signal fires once per user interaction, not
    twice (no feedback loop between the slider and the spinbox).
- Live screenshot: numeric options visibly show a slider track
  with a draggable thumb.

---

## 3. "WHERE THE FUCK ARE MY TABS?" — QTabWidget at the top of the advanced groups card

### Current state

`_build_advanced_groups` at `qt_app/app/pages/run.py:308` uses one
`CollapsibleGroup` per group (Context / KV-cache, GPU / offload,
Performance, Sampling, Debug / logging, Server / API, Advanced,
Raw extra args). The user explicitly asked for tabs in Phase 11
§5; I shipped `CollapsibleGroup` instead and the user has been
frustrated. The fix: real `QTabWidget`.

### Fix

A `QTabWidget` at the top of the advanced card. Tabs are the group
names. Click a tab → the content below switches to that group's
options. Search box and "Only changed" filter pill at the top
filter the option cards across all tabs (hidden cards are
`setVisible(False)`, so a tab with 0 visible options is empty
but still clickable).

```text
+----------------------------------------------------+
|  Context / KV   |   GPU / offload  |  Performance  |  <-- tab bar
+----------------------------------------------------+
|                                                    |
|   ctx_size    [====slider=====] [spinbox]          |
|   cache_type_k [f16 ▾]                             |
|   cache_type_v [f16 ▾]                             |
|   defrag_thold [====slider====] [spinbox]          |
|   flash_attn  [auto ▾]                             |
|                                                    |
+----------------------------------------------------+
```

The first tab (Performance) is selected by default. Tabs are
scrollable if there are more than fit in the bar (QTabBar's
`setUsesScrollButtons(True)`).

### Files

- `qt_app/app/pages/run.py:_build_advanced_groups` (line 308)
- `qt_app/app/theme.py` — small QSS additions for the tab widget
  (selected tab has accent underline, unselected are muted)

### Acceptance

- The advanced groups card has a `QTabWidget` at the top.
- Tabs are labeled "Performance", "Context / KV-cache",
  "GPU / offload", "Sampling", "Debug / logging", "Server /
  API", "Advanced", "Raw extra args" (one per
  `LLAMA_OPTION_CATALOG.group`).
- Clicking a tab shows that group's options. Clicking Performance
  first by default.
- Search box and "Only changed" filter pill at the top of the
  card still operate on the flat `_option_cards` dict (filter
  applies across all tabs).
- A new `smoke_section14.py`:
  - `RunPage`'s advanced card has a `QTabWidget`.
  - Tab count ≥ 5 (one per group).
  - Switching the tab index changes the visible tab's content.

---

## Order of execution

1. Section 0: QSS regression smoke (already done as part of the
   pre-plan fix). Add the smoke to `smoke_section14.py`.
2. Section 1: 2-column main settings table.
3. Section 2: `SliderSpinBox` / `SliderDoubleSpinBox` widget,
   swap into `_make_editor` and `_make_schema_editor`. Add
   `min_value` / `max_value` / `step` to `LlamaOption`.
4. Section 3: `QTabWidget` for advanced groups.
5. Verification: full smoke bundle + new `smoke_section14.py`
   covering all three changes + the QSS regression check.
6. Live launch + screenshot pass.

---

## Verification

- `python -m compileall -q qt_app` passes.
- All 11 section smokes + 34+ service checks + 8 mmproj-path
  tests still pass.
- New `smoke_section14.py`:
  - **QSS parses cleanly**: `app.setStyleSheet(theme.build_stylesheet())`
    does not emit any Qt warning.
  - `RunPage`'s main settings card has exactly 16 `OptionCard`s
    laid out in 2 columns x 8 rows (verify the `QGridLayout`
    `rowCount` and `columnCount`).
  - `_make_editor` for `OptionKind.INTEGER` returns a
    `SliderSpinBox`; for `OptionKind.FLOAT` returns a
    `SliderDoubleSpinBox`. The composite's `setValue(v)` updates
    both internal widgets. The composite's `valueChanged` is
    emitted exactly once per user action.
  - `RunPage`'s advanced groups card has a `QTabWidget`. Tab count
    ≥ 5. Switching the tab index changes the visible tab.
- Live screenshot:
  - Main settings card shows 2 columns of options, all visible
    without scrolling.
  - Numeric options visibly show a slider track with a draggable
    thumb alongside the spinbox.
  - Advanced groups are a row of tabs at the top; click a tab,
    the content below switches to that group's options.

---

## Risks

- `SliderSpinBox` is a composite widget. The composite MUST
  re-emit `valueChanged` once per user interaction; if both the
  slider and the spinbox are connected, a `setValue` from one
  triggers the other, which triggers the first again. The
  implementation MUST block signals on the secondary widget during
  the set-from-primary pass.
- The 2-column main settings layout is a real `QGridLayout` (2
  columns, 8 rows). On narrow windows (< 720 px) the right
  column may clip; we add a `setMinimumWidth(720)` to the
  central area to prevent this.
- `QTabWidget` adds a tab bar that may scroll horizontally if
  there are many groups. `setUsesScrollButtons(True)` handles
  this.

---

## Non-goals

- The Library, Profiles, Settings, and Diagnostics pages are
  unchanged.
- The argument search and "Only changed" filter behaviour is
  unchanged: they filter the option cards across all tabs.
- The "Reset to defaults" and "Apply Preset" buttons are
  unchanged.
- The save/load flow and profile persistence are unchanged.
