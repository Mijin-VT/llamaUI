# Planner Report

## Status
ready

## Rationale
The locator evidence pinpoints a single unsafe `thread.started.connect(job.run, Qt.ConnectionType.QueuedConnection)` in `download_service.py:488` — the same PySide6 mis-dispatch anti-pattern already documented in `discover.py:306-310`. The in-repo safe form (`thread.started.connect(lambda: worker.run(), …)`) is already used by the search worker (`discover.py:300`) and the card worker (`discover.py:407`). The crash surface is the `run` slot landing on the GUI thread while the `quit → job.deleteLater → thread.finished → thread.deleteLater` chain races QApplication teardown, producing the `QObject: shared QObject was deleted directly` warning and SIGBUS. The xdg portal "app ID" warning is environmental (`setDesktopFileName("llamaUI")` is set in `application.py:47` with no matching `.desktop` file installed) and explicitly non-causal. The existing `smoke_download_manager.py` already records worker thread IDs and asserts `len(worker_tids) >= 3` (downloads ran on threads other than main), which is a sufficient regression guard — no test edits are justified. Fix is a one-line wiring change in `_start`; preserves parent-less `_DownloadJob`, preserves `moveToThread`, does not reparent anything.

# Task Packet

## User Goal
Fix the crash when downloading a HuggingFace model from the Discover page (`QObject: shared QObject was deleted directly` warning, SIGBUS on teardown). The xdg portal "app ID" warning must be treated as environmental/non-causal and is explicitly out of scope.

## Mode
general-coding

## Relevant Locations
- file: `qt_app/app/services/download_service.py`
  symbol: `DownloadManager._start`
  approximate lines: 468–490 (crash-relevant block; the specific line to change is **488**)
  stable anchor: `thread.started.connect(job.run, Qt.ConnectionType.QueuedConnection)` at line 488 (replace with `thread.started.connect(lambda: job.run(), Qt.ConnectionType.QueuedConnection)`)
  reason: the unsafe direct-slot form is the in-repo flagged PySide6 mis-dispatch anti-pattern; with `QThread(self)` (parent = GUI-thread manager) the `run` slot can be dispatched to the GUI thread, and the `quit → job.deleteLater → thread.finished → thread.deleteLater` chain then races QApplication teardown.
  confidence: high
- file: `qt_app/app/pages/discover.py`
  symbol: `_SearchWorker.run` / `_CardWorker.run` wiring
  approximate lines: 297–311 (search), 404–412 (card)
  stable anchor: `thread.started.connect(lambda: worker.run(), Qt.ConnectionType.QueuedConnection)` at line 300 and line 407
  reason: reference implementation of the safe pattern already used in-repo; the download worker must be aligned with this.
  confidence: high
- file: `qt_app/app/application.py`
  symbol: `create_app`
  approximate lines: 34–47
  stable anchor: `app.setDesktopFileName("llamaUI")` at line 47
  reason: confirms the xdg portal "app ID" warning is environmental (no installed `llamaUI.desktop` file matches). Non-causal — no edit.
  confidence: high
- file: `qt_app/tests/smoke_download_manager.py`
  symbol: `_FakeService` / `main`
  approximate lines: 30–60 (fake), 130–170 (background-thread assertion)
  stable anchor: `worker_tids = fake._thread_ids - {main_tid}` and `check(len(worker_tids) >= 3, …)`
  reason: existing regression guard — if the mis-dispatch regresses, `job.run` lands on the GUI thread, `DownloadService().download(...)` records the main `threading.get_ident()`, the subtract empties `worker_tids`, and the assertion fails. No edit required; the test already documents the regression.
  confidence: high

## Allowed Edit Files
- `qt_app/app/services/download_service.py` — exactly **one** line (line 488) inside `DownloadManager._start`.

## Read-Only Context Files
- `qt_app/app/pages/discover.py` — pattern reference (safe lambda form at lines 300, 407; unsafe-pattern comment at 306–310).
- `qt_app/tests/smoke_download_manager.py` — existing regression guard (worker-tid assertion at the `len(worker_tids) >= 3` check). Read-only; the existing test already protects against this regression.
- `qt_app/app/application.py` — confirms the portal app ID warning is non-causal.

## Required Change
In `qt_app/app/services/download_service.py`, inside `DownloadManager._start` (the method beginning at line 468, comment `# No parent on the job: …` at line 469), change exactly one line:

Replace:
```python
thread.started.connect(job.run, Qt.ConnectionType.QueuedConnection)
```
with:
```python
thread.started.connect(lambda: job.run(), Qt.ConnectionType.QueuedConnection)
```

That is the entire fix. Do not:
- reparent `_DownloadJob` (the `# No parent on the job:` comment at line 469 documents the constraint — `moveToThread` requires no parent).
- reparent the `QThread` (it must remain `QThread(self)` so the manager tracks it for shutdown).
- touch any other connect/disconnect, signal, or slot.
- edit `discover.py` (its search/card workers already use the safe form).
- edit `smoke_download_manager.py` (the existing `worker_tids` check is the regression guard).
- install a `.desktop` file or alter `setDesktopFileName` (the xdg portal warning is environmental and explicitly out of scope).

## Non-Goals
- The xdg-portal "app ID" warning is environmental (no installed `llamaUI.desktop`); do not attempt to silence it from this task.
- Restructuring the worker pattern (e.g. moving to `QtConcurrent.run` or a generic worker pool) is out of scope; the lambda wrapper is the minimal, in-repo-approved fix.
- Disconnecting `job.progress` / `job.finished` on shutdown and adding a `wait()` in `DownloadManager` shutdown is described as "optional hardening" in the locator's stop recommendation. The one-line fix is sufficient to address the reported crash; do not bundle optional hardening into this packet.
- Any UI / Discover-page changes.
- Any test additions or edits.

## Validation
Commands:
- `python qt_app/tests/smoke_download_manager.py` — headless, exits 0 on success. Runs the existing regression guard that records worker thread IDs via the patched `DownloadService` and asserts `len(worker_tids) >= 3` (downloads did **not** run on the GUI/main thread).
- `python -m pytest qt_app/tests/smoke_download_manager.py -q` — same script under pytest if the project wires it; equivalent coverage.

Expected result:
- `smoke_download_manager.py` prints `=== All DownloadManager smoke tests passed ===` and exits 0.
- No `QObject: shared QObject was deleted directly` warning, no `QThread: Destroyed while thread is still running`, no SIGBUS / bus error in the run.

Manual repro (requires display; cannot be automated headless in this environment — record in the worker return):
1. `python qt_app/main.py`
2. Open the **Discover** page.
3. Search for a small GGUF model (e.g. `qwen2.5-0.5b-instruct-gguf` or any small public repo).
4. Select a file row in the file combo and click **Download selected file**.
5. With `QT_LOGGING_RULES="*.debug=true"` set, watch stderr: the `QObject: shared QObject` / `QThread: Destroyed while thread is still running` warnings should no longer appear on the download path.
6. The xdg-portal "Could not find the name for .desktop file" / `qt.qpa.services` "app ID" warning may still appear — that is the environmental warning and is **expected** to remain after this fix (per the non-causal classification).
7. Let the download complete and confirm the Discover page navigates to **Library** and the new model is listed (this exercises the manager-shutdown race that was the original crash surface).

Headless alternative for the manual repro is not available because the crash repro requires the full Discover UI; rely on the smoke test for CI and the manual run for end-to-end confirmation.

## Stop Conditions
Stop and report if:
- line 488 already uses the lambda form (the fix is already applied — do nothing).
- the requested change cannot be made without editing `discover.py` or the test file (it should not; both are read-only here).
- `smoke_download_manager.py` fails after the change — re-read the failure; if it indicates the mis-dispatch still occurs, the lambda wrapper may not have been preserved (e.g. an auto-formatter collapsed it back to a direct slot); stop and report rather than attempting further edits.
- the portal `.desktop` warning is asked to be fixed in the same packet (it is out of scope — escalate).
- the user requests reparenting of `_DownloadJob` or `QThread` (those would break `moveToThread`; stop and report).

## Required Return Contract
Return only a task-focused summary. Do not include transcript, tool logs, raw file dumps, large code blocks, or broad unrelated issues. Include status, files inspected/changed, validation evidence, blockers, and task-specific risks. Specifically: confirm the one-line edit at `download_service.py:488`, confirm the smoke test was run headless and passed, and explicitly call out that the xdg portal warning was not addressed and remains expected.
