# Phase 15 — Aligned, non-cropping panels

## The two real bugs

### Bug A: `_refit_advanced_panel` measures wrong height

`_refit_advanced_panel` uses `inner_layout.heightForWidth(page.width())`.
This is a `FlowLayout` call but the `FlowLayout` overrides
`heightForWidth` to return the height given the actual width. The
issue: when `_do` is called via `QTimer.singleShot(0)`, the page
widget has not yet been laid out at its current width, so the
`FlowLayout`'s `widthCache` (or the per-row wrap state) is stale.
The result: measured height is too small, body is set to 98 px, the
tab content overflows and gets clipped by the surrounding card.

### Bug B: option layout is a FlowLayout, not a grid

The current `FlowLayout` in each tab page wraps cards
imprecisely. The user wants a strict 2-column grid (or 3-column at
wide widths) where every option's label/flag/editor line up
vertically across rows. This is what the user asked for in Phase 14
but I delivered a `FlowLayout` instead of a real table.

The user said in the original Phase 14 request: "Split it into
seprate columns like a table, and make sure each arguement is
aligned appropriatelly. It will be still dynamically scaled based on
the Group but at least they will stay aligned."

The 16 main options are in a 2-column grid (per Phase 14 §1). The
advanced tab options also need a 2-column grid. Not FlowLayout.

## Cross-cutting: every panel, every window, every page

The user said "check all the panels in all the windows and all the
groups of all the other panes, like the libray, discover etc, that
are also not cropped and are aligned even when the window of the
app is mall. Vertical scrollbar are fine. Horizontal is not ok
unless it is a table or a webside parsed."

So this is a sweep across all pages, not just the Run page:

- **Library**: model picker dropdown (single column, fine), detail
  card layout (one card, fine), stat tiles row, profile list.
- **Discover**: search row, results table, file picker, download
  queue, model card. The "results table" uses a `QTableWidget` —
  is it scrolled horizontally? Need to verify.
- **Profiles**: model picker + profile list + form. The form is a
  `QFormLayout` (label | editor) which is the natural pattern.
- **Settings**: stack of form cards. Each card is a `QFormLayout`.
  Need to verify columns line up.
- **Diagnostics**: stat tiles + 3 cards. Cards are in a row with
  `QHBoxLayout` and may shrink below content width on small
  windows.
- **Run**: the 4 cards (hero, main, advanced, logs).

The rule: **vertical scroll is fine. Horizontal scroll is not OK
unless the content is intrinsically a table or a web-page
parser** (e.g. a JSON tree view, the model card, or a multi-column
log viewer).

## Plan

### 1. Replace `FlowLayout` in advanced tab pages with a strict 2-column `QGridLayout`

In `qt_app/app/pages/run.py:_build_schema_advanced` and
`_build_catalog_advanced` (lines 451-540-ish), the per-tab page
hosts a `FlowLayout`. Replace the `FlowLayout` (and the wrapping
`flow_widget` `QWidget` host) with a `QGridLayout` directly on the
tab page:

- 2 columns. Each option is one cell.
- Row-major: option 0 at (0,0), option 1 at (0,1), option 2 at
  (1,0), etc.
- `setColumnStretch(0, 1); setColumnStretch(1, 1)` so both columns
  have equal width.
- `setHorizontalSpacing(10); setVerticalSpacing(8)`.
- The `OptionCard` is the cell content.

The grid gives:
- Every option is a fixed size, no FlowLayout wrap surprises.
- A 6-option tab produces 3 rows × 2 cols; a 4-option tab produces
  2 rows × 2 cols.
- The 2-column layout is responsive at the page level: when the
  page is wide, columns stretch; when narrow, both columns shrink
  equally.

For the "Raw extra args" tab which has a single text input, the
grid still works (1 cell, 1 row).

### 2. Fix `_refit_advanced_panel` to use the active page's grid sizeHint directly

In `qt_app/app/pages/run.py:_refit_advanced_panel` (line 397), the
helper computes the active page's height via
`inner_layout.heightForWidth(page.width())`. Replace with:

```python
# Force the inner grid to lay out at the current width, then read
# its actual height. This avoids the stale-cache problem where
# heightForWidth returns a value from before the page was last
# laid out.
inner_layout = page.layout()
if inner_layout is None:
    h = 80
else:
    page.layout().activate()  # forces layout at current geometry
    # heightForWidth + the minimum sizeHint; use the larger of the
    # two in case the layout has a fixed-height constraint.
    try:
        h = inner_layout.heightForWidth(page.width())
    except Exception:
        h = page.sizeHint().height()
    if h <= 0:
        h = page.minimumSizeHint().height()
    if h < 80:
        h = 80
```

The `page.layout().activate()` call is the key. It forces a layout
recompute at the page's current width, after which `heightForWidth`
returns the correct value.

### 3. Sweep all pages for horizontal scroll

For each page (`Library`, `Discover`, `Profiles`, `Settings`,
`Diagnostics`, `Run`), audit and confirm:

- The page is a `QScrollArea` with `setWidgetResizable(True)`.
- No inner widget has `setMinimumWidth(...)` that exceeds the
  viewport.
- No `QTableWidget` or `QTreeWidget` has a horizontal scrollbar in
  normal use. (Tables are allowed horizontal scroll because the
  user explicitly accepted "table" content.)
- All `Card` widgets use a `QVBoxLayout` or `QHBoxLayout` with
  `setSizePolicy(Preferred, Maximum)` so they don't push their
  parent to a min-width.

Concretely, edit each page to:
- Wrap each `Card` in a way that its `sizePolicy` is `Preferred,
  Maximum` (so it doesn't enforce a min-width).
- Use `setMinimumWidth(0)` and `setMaximumWidth(QWIDGETSIZE_MAX)`
  on any nested widgets.
- Audit `QTableWidget` usage: only the Discover results table
  (which is a real table) uses one, so it's allowed.

### 4. Verify the hero card (runtime header) does not push the window wide

`RunPage._build_runtime_header` adds Save/Save As/Duplicate/Reset/
Preset/Apply Preset/Reset to defaults + Start/Stop/Restart/Load via
API all in a single `QHBoxLayout`. On a narrow window this row
gets compressed and may force a horizontal scroll. Wrap it in a
`QScrollArea` with `setHorizontalScrollBarPolicy(ScrollBarAsNeeded)`
so the toolbar scrolls horizontally on small windows but the page
itself does not.

## Files

- `qt_app/app/pages/run.py` (advanced groups + hero)
- `qt_app/app/pages/library.py` (audit + fix any horizontal-scroll)
- `qt_app/app/pages/discover.py` (audit + fix)
- `qt_app/app/pages/profiles.py` (audit + fix)
- `qt_app/app/pages/settings.py` (audit + fix)
- `qt_app/app/pages/diagnostics.py` (audit + fix)
- `qt_app/app/widgets/cards.py` (set `Card` size policy to
  `Preferred, Maximum` globally)
- `qt_app/app/widgets/flow.py` (mark as deprecated; no longer used
  in Run page; keep for back-compat)
- `qt_app/tests/smoke_section15.py` (new)

## Acceptance

- `python -m compileall -q qt_app` passes.
- All 12 existing section smokes + 34+ service checks + 8
  mmproj-path tests still pass.
- New `smoke_section15.py`:
  - For each page (Library, Discover, Profiles, Settings,
    Diagnostics, Run), at a 900×720 viewport, no inner widget has
    a horizontal scrollbar. The `QScrollArea` (if any) has
    horizontal scroll policy = `ScrollBarAsNeeded` (no bar shown
    by default).
  - The advanced panel's `FlowLayout` is gone. The per-tab page
    has a `QGridLayout` with `columnCount() == 2`.
  - `_refit_advanced_panel` produces a body height that contains
    the active tab's actual content (verified by setting the body
    height to the measured height and asserting the body geometry
    contains the active page's geometry).
- Live screenshots:
  - Run page, Performance tab, at 900×720 — all 9 options visible
    in a clean 2-col grid; no cropping.
  - All other pages — no horizontal scrollbar at 900×720.

## Risks

- Replacing `FlowLayout` with `QGridLayout` may make some tabs
  look different. The trade-off: 100% grid alignment vs. 100%
  flow wrap. The user explicitly asked for the grid.
- `_refit_advanced_panel`'s `activate()` call may trigger a brief
  layout cycle. This is fine; it happens on a single-shot
  QTimer so it's not in the paint event.
- Setting `Card` to `Preferred, Maximum` size policy means cards
  will not enforce a min-width even if the user shrinks the
  window. That's the right behavior for these cards; the page's
  `QScrollArea` handles overflow.

## Non-goals

- The library / discover / profiles / settings / diagnostics
  page structure does not change. Only the alignment and
  size-policy of inner widgets.
- The catalog and runtime schema are unchanged.
- The save/load flow is unchanged.
- The runtime controller is unchanged.
