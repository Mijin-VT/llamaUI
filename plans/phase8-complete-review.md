# Phase 8 Complete Review

## Status

Phase 8 runtime/process/API control is implemented and reviewed with fixes applied.

## Implemented

- Local `llama-server` process controller with start/stop/restart.
- Argv builder from config + selected model + selected profile.
- Port conflict detection before launch.
- Stdout/stderr log capture into a thread-safe log buffer.
- API client for health/status and model switching attempts.
- API switch returns restart-required fallback when hot-load endpoint is unavailable.
- Run page now shows model/profile selectors, command preview, runtime status, health polling, log search/filter/clear, and restart fallback messaging.
- Inspector no longer shows fake runtime data.

## Review findings fixed

- Removed direct Qt widget updates from background log threads; Run page now reads the controller's log buffer on a QTimer.
- Fixed `stop()` re-entrant/ownership issues around status snapshots.
- Runtime switch fallback handles unreachable servers and non-supported endpoints cleanly.
- Run page polls runtime health and shows endpoint/model/profile state.
- Added bounded log history and log filtering controls.
- Removed fake static inspector runtime state.

## Verification

```text
python -m compileall -q qt_app
```

passed.

Runtime smoke:

```text
runtime_smoke=ok
```

Baseline service smoke:

```text
python qt_app/tests/smoke_services.py
```

passed.

Qt smoke:

```text
platform= wayland
visible= True
rc= 0
```
