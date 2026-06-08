# Phase 6 Complete Review

## Status

Phase 6 HuggingFace discovery/download is implemented and reviewed with fixes applied.

## Implemented

- Real HuggingFace GGUF search via `filter=gguf`, `full=true`, model detail fallback, and tree-size fallback.
- Live searches for `qwen`, `gemma`, and `llama` return non-empty GGUF repos.
- Search hydration runs in parallel in the service.
- Discover UI search runs in a QThread so the Qt main thread does not block.
- Discover page uses interactive `FilterPill` controls.
- Discover page shows repo rows with downloads/likes/fit/files/smallest size.
- Download buttons download the smallest non-split file in a background QThread.
- Download service writes files atomically and persists `LocalModel` metadata through `LibraryStore`.
- Download service supports resume via HTTP Range when a `.part` file exists and no SHA verification is requested.
- Download metadata now includes license, base model, tags, gated/private, and cached model card path when provided.
- Split GGUF repos are detected; the UI refuses one-part split downloads rather than producing an unusable local model.

## Review findings fixed

- Fixed UI-thread blocking search with QThread worker.
- Restored `NotImplementedHfSearchService` as a true no-op.
- Reduced serial N+1 cost by parallelizing hydration and not fetching README during search.
- Hardware fit now uses detected VRAM/RAM thresholds when available.
- Wired download UI to `DownloadService`.
- Replaced static chips with interactive `FilterPill`s.
- Search service uses saved HF token from `ConfigStore` in Discover.
- Download metadata supports card cache path and rich HF metadata.
- Download URLs use repo default branch when available.
- `dataclasses.replace()` used for frozen `HfFile` size updates.
- Library upsert preserves `created_at` for existing models.

## Verification

```text
python -m compileall -q qt_app
```

passed.

Live HF search:

```text
qwen ok 3
gemma ok 3
llama ok 3
hf_search_smoke=ok
```

Download/metadata smoke:

```text
download_metadata_smoke=ok
```

Baseline service smoke:

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

Qt smoke:

```text
platform= wayland
visible= True
rc= 0
```

## Remaining non-blocking follow-up

- Full split-set download should be implemented as a richer action; current UI refuses unsafe one-part downloads.
- Rich model-card display is Phase 7.
