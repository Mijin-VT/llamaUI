# Phase 13 — Clean server stop

The current `LlamaServerController.stop()` does SIGTERM → wait →
SIGKILL → wait, but a few things go wrong:

1. **Process group not killed**. `llama-server` can spawn worker
   processes (e.g. the GGML compute pool, the HTTP server). Killing
   the parent with `proc.kill()` only kills the parent. The
   children keep running, hold the port, hold the GPU memory.

2. **No zombie reap**. If `proc.kill()` doesn't reap the process
   (e.g. because the process is in `D` uninterruptible state on a
   hung NFS mount), the `wait` returns early and the state is left
   as `STOPPING` instead of `STOPPED`, but the controller has
   already cleared `_process`. Restart then reuses a stale port.

3. **No force-kill backstop**. After SIGKILL, if the process is
   still alive (rare but possible on locked-up kernels), there is
   no further attempt — the controller just gives up.

## Change

In `qt_app/app/services/runtime.py`:

### A. `start()` — run in own process group

In `LlamaServerController.start`, add `start_new_session=True` to the
`subprocess.Popen` call so `llama-server` and any of its children
end up in a new session and process group. Then we can kill the
whole group with `os.killpg`.

### B. `stop()` — clean kill chain

Replace the body with:

1. Set `_stop_health` so the health poll stops.
2. Acquire the lock; capture `proc` and `pgid` (process group id);
   bail if no live process.
3. State = STOPPING. Release the lock.
4. Send `SIGTERM` to the **process group** via `os.killpg(pgid, SIGTERM)`.
5. Wait up to `graceful_timeout` (default 5s) for `proc.wait()`.
6. If alive, send `SIGKILL` to the **process group** via `os.killpg`.
7. Wait up to `kill_timeout` (default 3s) for `proc.wait()`.
8. If still alive, log a warning and force-`os.killpg(SIGKILL)` one
   more time. This handles the rare stuck-kernel case.
9. Acquire the lock; if `proc.returncode is not None`, mark
   STOPPED, clear pid/process/api_client. If still `None`, mark
   ERROR with a clear message ("process did not exit after
   SIGKILL; check `ps` and `nvidia-smi` for orphans").
10. Return the new status.

### C. `restart()` — hard-fail-safe

If `stop()` returns ERROR (process didn't die), `restart()` must
NOT reuse the port. The current `restart()` calls `self.stop()` and
then `self.start()`. The new `stop()` already raises via the state
set to ERROR + last_error, and `start()` will see the port is
occupied, so the user gets a clear error.

## Acceptance

- `python -m compileall -q qt_app` passes.
- `python qt_app/tests/smoke_services.py` still passes.
- All 10 section smokes still pass.
- A new `smoke_section13.py`:
  - Construct a `LlamaServerController`.
  - Start a fake server (`["/bin/sh", "-c", "sleep 60"]`).
  - Stop it. Assert state == STOPPED, pid is None.
  - Assert the underlying subprocess's `returncode is not None`.
  - Start another fake server, then start a child via
    `subprocess.Popen(["/bin/sh", "-c", "sleep 60"], preexec_fn=...)`
    in the same group; call `controller.stop()`; assert both the
    parent and the child are dead.
  - Stress: start a server that ignores SIGTERM (a shell loop that
    traps signals), call `controller.stop(timeout=1.0)`, assert
    state == STOPPED within `kill_timeout + small slack`.
- Live: clicking Stop in the UI while a 27 GB Qwen is loaded
  releases VRAM within a few seconds; the next Start succeeds
  without "port in use" or "model already loaded" errors.

## Risks

- `start_new_session=True` makes the child the leader of a new
  process group AND a new session. The console mode (if the
  user later wants to attach a debugger) might be affected, but
  llama-server doesn't have a debugger attach UI in this app.
- `os.killpg` on a process group I don't own is unsafe in
  shared environments. We only do this for the process group we
  just created, so it's fine.
- On Windows, `start_new_session` is ignored and `os.killpg` is
  not available. Wrap both in `sys.platform != "win32"` guards.
