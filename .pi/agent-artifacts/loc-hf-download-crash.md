# Locator Report

## Summary
Crash surface for the "Discover page → Download selected file" flow is the `DownloadManager` worker / `QThread` lifetime chain in `qt_app/app/services/download_service.py`, fed by `DiscoverPage._download_selected` in `qt_app/app/pages/discover.py`. The `thread.started.connect(job.run, Qt.QueuedConnection)` form (file-1 line 488) is the in‑repo flagged "PySide6 mis-dispatch" anti‑pattern; combined with no‑parent `_DownloadJob` and threads parented to the GUI‑thread manager, it yields the `QObject: shared QObject was deleted directly` warning and the SIGBUS core dump when the job/thread teardown races the GUI shutdown.

## Timing
- elapsed: ~60 s
- verification calls: 7 (grep x3, read x4, codemap_context not needed — hits already pinpointed by grep)
- files read (windowed): 5 — `discover.py` 130–250 / 270–400 / 400–560, `download_service.py` 1–30 / 85–195 / 230–320 / 340–510, `main.py` (full, 46 lines), `application.py` (grep)
- full-file reads: 0
- tool path: grep-first; codemap_context not required (paths identified by exact-symbol search)

## Confidence
high

## Relevant Locations
1. `qt_app/app/services/download_service.py`
   - symbols: `DownloadManager`, `_DownloadJob`, `_start`, `_on_finished`, `HfDownloadRequest`
   - approximate lines:
     - `_DownloadJob` class: 343–404 (signals `progress`/`finished`; `run` at 372–403; uses blocking `urllib.request.urlopen` via `DownloadService().download`)
     - `DownloadManager.__init__`: 421–431
     - `DownloadManager._start`: **468–490** — the crash-relevant block
     - `DownloadManager._on_finished`: 495–507
   - stable anchors:
     - `class DownloadManager(QObject):`        line 408
     - `def _start(self, job_id: str, request: HfDownloadRequest) -> None:` line 468
     - `thread.started.connect(job.run, Qt.ConnectionType.QueuedConnection)` line 488
     - `job.finished.connect(thread.quit, Qt.ConnectionType.QueuedConnection)` line 482
     - `job.finished.connect(job.deleteLater, Qt.ConnectionType.QueuedConnection)` line 483
     - `thread.finished.connect(thread.deleteLater, Qt.ConnectionType.QueuedConnection)` line 484
     - `# No parent on the job:` comment  line 469
   - why relevant: the worker is started with the exact `thread.started → job.run` form that the in-repo comment in `discover.py:306–310` calls out as a PySide6 mis-dispatch bug ("can mis-dispatch `run` onto the GUI thread when the QThread is parented to a widget"). `QThread(self)` parents the thread to the GUI-thread manager; the job has **no parent** and is moved to the worker thread; the `quit` → `job.deleteLater` → `thread.finished` → `thread.deleteLater` chain races the worker thread’s `exec()` shutdown and QApplication teardown, producing the "shared QObject was deleted directly" warning and SIGBUS.
   - evidence: `grep deleteLater|shared QObject|QObject|QThread` returned these exact lines; windowed `read` of 468–502 and 340–510 confirmed the wiring.

2. `qt_app/app/pages/discover.py`
   - symbols: `DiscoverPage`, `_SearchWorker`, `_CardWorker`, `_download_selected`, `_on_manager_finished`
   - approximate lines:
     - `_SearchWorker`/`_CardWorker`: 133–145
     - `DiscoverPage.__init__`: **148–169** — manager created *before* `super().__init__`, then reparented
     - `build()` (manager signal wiring): **266–269** — `self._download_manager.progress.connect(self._on_manager_progress)` etc.
     - `_search` QThread wiring: 297–311 (uses the safe `lambda: worker.run()` form, line 300)
     - `_load_card` QThread wiring: 404–412 (same safe lambda form, line 407)
     - `_download_selected` (the user-facing trigger): 416–485
     - `_on_manager_finished` (navigate to library on first success): 520–542
   - stable anchors:
     - `self._download_manager = DownloadManager(LibraryStore.default())`  line 167
     - `self._download_manager.setParent(self)`                            line 169
     - `self._download_manager.progress.connect(self._on_manager_progress, …)` line 266
     - `def _download_selected(self) -> None:`                              line 416
     - `job_id = self._download_manager.enqueue(request)`                   line 474
   - why relevant: Discover is the only place `_download_manager.enqueue(...)` is called from a UI page; this is the exact user action in the crash repro. Note the in-page search/card workers use the **safe lambda wrapper** (`thread.started.connect(lambda: worker.run(), Qt.QueuedConnection)`) at lines 300 and 407, while the download worker does NOT — the download flow uses the unsafe direct form in `download_service.py:488`. The `manager.setParent(self)` reparent plus threads-as-children-of-manager is what enables the parented-QThread mis-dispatch.
   - evidence: `grep` on `progress|finished|status_changed|queue_changed|_on_manager|_download_manager|connect` in `discover.py` returned lines 266–269 (the only connect of `_download_manager.*`); windowed `read` 130–250 / 270–400 / 400–560 confirmed wiring.

3. `qt_app/main.py` + `qt_app/app/application.py`
   - symbols: `create_app`, `QApplication`
   - approximate lines: `application.py` 34–47; `main.py` 34–46
   - stable anchors:
     - `app.setApplicationName("llamaUI")`             `application.py:43`
     - `app.setApplicationDisplayName("llamaUI")`     `application.py:44`
     - `app.setOrganizationName("llamaUI")`           `application.py:45`
     - `app.setDesktopFileName("llamaUI")`            `application.py:47`
   - why relevant: the `qt.qpa.services` portal "app ID" warning is environmental — `setDesktopFileName("llamaUI")` is set, but no matching `.desktop` file is installed on the system, so `xdg-desktop-portal` warns. It is **not** the cause of the crash; it is just noise that precedes the real bug.
   - evidence: `grep setApplicationName|setDesktopFileName|qApp|QApplication` returned the identity lines; `read` of `main.py` showed no extra QApplication setup.

## Allowed Edit Scope Recommendation
- `qt_app/app/services/download_service.py` (DownloadManager._start, lines 468–490) — primary fix surface.
- `qt_app/app/pages/discover.py` (no edits required for the crash fix; the in-page search/card workers are already correct, so no change needed there — the fix is to make the download worker match the safe pattern).

## Read-Only Context Recommendation
- `qt_app/app/services/download_service.py` (full file, ~520 lines — currently only windowed; a full read is <120 lines would fit the budget, but the relevant block is 408–510)
- `qt_app/app/pages/discover.py` (the section 148–170 for `__init__` ordering is the other important read)
- `qt_app/tests/smoke_download_manager.py` (existing validation harness; not yet read, but referenced by the codemap index)

## Validation Targets
- tests:
  - `qt_app/tests/smoke_download_manager.py` — existing harness that constructs a `DownloadManager` and drives `enqueue`/`cancel`; run this first to confirm the manager itself is sound in isolation, then extend it to assert: (a) `thread.started` does not dispatch `run` on the GUI thread, (b) the job+thread are fully torn down after `finished`, (c) no `QObject: shared QObject was deleted directly` warning is emitted during shutdown.
- commands:
  - `python qt_app/tests/smoke_download_manager.py`
  - `python qt_app/main.py` (repro the user-reported path: open Discover → search → click "Download selected file")
  - `python -m pytest qt_app/tests/smoke_download_manager.py -q` (if pytest is wired in)
- manual checks:
  - With `QT_LOGGING_RULES="*.debug=true"`, watch for "QObject: shared QObject" / "QThread: Destroyed while thread is still running" / "QObject::deleteLater: Shared QObject" appearing only on the download path (not on search or model-card load).
  - Run the same repro twice: once with the existing `thread.started.connect(job.run, Qt.QueuedConnection)` (crash) and once after switching to the lambda-wrapper form used in `discover.py:300, 407` to confirm the crash is gone.

## Risks / Unknowns
- The portal "app ID" warning is environmental (no installed `.desktop` file matching `llamaUI`); it can be silenced by installing a `llamaUI.desktop` file or by not calling `setDesktopFileName` when no file is present — but it is not the cause of the crash.
- `urllib.request.urlopen` is blocking and runs on whatever thread `run()` ends up on; even after the lifetime fix, the GUI may freeze during download if `run` is mis-dispatched to the GUI thread. A follow-up could move the I/O to a `QThread` with a proper worker pattern (or `QtConcurrent.run`) — the in-repo `discover.py:306–310` comment already documents the safe pattern.
- The `_DownloadJob` is intentionally parent-less, so a successful fix must preserve the `moveToThread` semantics (do not reparent the job).
- Three downloads fire concurrently (split-GGUF companion files), so the QApplication teardown race is most likely to be hit on the file that finishes first/last while the user is still on the Discover page; this matches the user’s observation of the crash on completion.

## Stop Recommendation
Proceed. Implementation should:
1. Change `download_service.py:488` from `thread.started.connect(job.run, Qt.ConnectionType.QueuedConnection)` to `thread.started.connect(lambda: job.run(), Qt.ConnectionType.QueuedConnection)` to match the in-repo safe pattern in `discover.py:300` and `discover.py:407`.
2. (Optional hardening) Disconnect `job.progress` / `job.finished` from the manager before allowing the manager to be destroyed, and ensure `thread.finished` is fully drained (e.g., give the worker thread a `wait()` in `DownloadManager` shutdown) so a `QApplication.exec()` return cannot race a half-deleted job.
3. Re-run `smoke_download_manager.py` and the manual repro.
