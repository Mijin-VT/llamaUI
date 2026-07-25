# Phase 7 Complete Review

## Status

Phase 7 Library/model-card work is implemented and reviewed with fixes applied.

## Implemented

- Local model scan service for configured models directory.
- Scans `.gguf` files, infers quant, records size, preserves existing HF/card metadata.
- Removes stale entries only when the missing file is actually under the configured models dir.
- Library page Rescan is wired to real scan service.
- Library page groups rows by HF repo or local folder.
- Library table shows model/path/size/quant/fit/profile count/HF repo.
- Selecting a model shows metadata, cached model card, tags, license, base model, and profiles.
- Detail actions exist: Run selection placeholder, Edit Profiles hook, Create Profile hook, Reveal File, Open HF.
- Cached model cards are read through `read_card_cache()`.

## Review findings fixed

- Fixed smoke test isolation and assertions.
- Added grouping by HF repo/folder.
- Added Create Profile action alongside Edit Profiles.
- Added hardware fit display.
- Added profile list in model detail.
- Fixed Library layout order to header → table → detail.
- Re-adds table title after re-render.
- Replaced fragile `startswith` stale-path detection with `Path.is_relative_to()`.
- Library quant inference now uses shared `infer_quant()`.

## Verification

```text
python -m compileall -q qt_app
```

passed.

```text
python qt_app/tests/smoke_services.py
```

passed, including library scan/quant/stale removal checks.

Qt smoke:

```text
platform= wayland
visible= True
rc= 0
```
