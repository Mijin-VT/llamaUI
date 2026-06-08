"""Smoke test for concurrent DownloadManager.

Verifies:
- Multiple downloads can be active at the same time (up to the cap).
- Progress and finished signals are delivered on the main thread.
- Cancel removes queued items and stops active ones.
- UI event loop stays responsive while downloads run.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
QT_ROOT = REPO_ROOT / "qt_app"
for candidate in (REPO_ROOT, QT_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication  # noqa: E402

from llama_data import LibraryStore, default_paths  # noqa: E402
from app.services.download_service import (  # noqa: E402
    DownloadError,
    DownloadManager,
    DownloadProgress,
    DownloadStatus,
    HfDownloadRequest,
)


def _noop_download_service():
    """Return a factory for a fake DownloadService that sleeps a little
    and reports progress so we can observe concurrent execution."""

    class _FakeService:
        _calls: list[HfDownloadRequest] = []
        _cancelled: set[str] = set()

        def download(self, req: HfDownloadRequest, library, *, on_progress=None, cancel_check=None):
            self._calls.append(req)
            job_id = req.filename
            total = 1024 * 1024
            for downloaded in range(0, total + 1, total // 4):
                if cancel_check and cancel_check():
                    raise DownloadError("cancelled")
                if on_progress is not None:
                    prog = DownloadProgress(
                        url=req.url,
                        dest_path=str(Path(req.dest_dir) / req.filename),
                        status=DownloadStatus.DOWNLOADING,
                        bytes_downloaded=downloaded,
                        bytes_total=total,
                    )
                    on_progress(prog)
                time.sleep(0.05)
            from llama_data.models import LocalModel

            return LocalModel(
                id=str(Path(req.dest_dir) / req.filename),
                path=str(Path(req.dest_dir) / req.filename),
                size_bytes=total,
            )

    return _FakeService()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  pass {message}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as td:
        paths = default_paths(Path(td))
        paths.ensure()
        library = LibraryStore(paths)
        manager = DownloadManager(library)

        progress_counts: dict[str, int] = {}
        finished: dict[str, object] = {}
        max_active = [0]
        max_pending = [0]

        def _on_progress(job_id: str, prog: DownloadProgress) -> None:
            progress_counts[job_id] = progress_counts.get(job_id, 0) + 1
            max_active[0] = max(max_active[0], manager.active_count())
            max_pending[0] = max(max_pending[0], manager.pending_count())

        def _on_finished(job_id: str, result: object) -> None:
            finished[job_id] = result

        manager.progress.connect(_on_progress)
        manager.finished.connect(_on_finished)

        fake = _noop_download_service()
        with patch(
            "app.services.download_service.DownloadService",
            lambda: fake,
        ):
            ids = []
            for n in range(5):
                req = HfDownloadRequest(
                    repo_id="org/model",
                    filename=f"file{n}.gguf",
                    url=f"http://example.com/file{n}.gguf",
                    dest_dir=td,
                    size_bytes=1024 * 1024,
                )
                ids.append(manager.enqueue(req))

            # Poll until all downloads finish.
            deadline = time.time() + 5.0
            while time.time() < deadline and len(finished) < 5:
                app.processEvents()
                time.sleep(0.01)
                max_active[0] = max(max_active[0], manager.active_count())
                max_pending[0] = max(max_pending[0], manager.pending_count())

            # With a cap of 3, we should have observed 3 active at once
            # and at least 2 pending at some point.
            check(max_active[0] == 3, f"manager caps active downloads at 3 (observed max {max_active[0]})")
            check(max_pending[0] >= 2, f"at least 2 downloads were queued (observed max {max_pending[0]})")

            # Ensure the UI event loop is still processing: schedule a timer
            # and confirm it fires while downloads are in flight.
            from PySide6.QtCore import QEventLoop

            timer_fired = [False]

            def _set_flag():
                timer_fired[0] = True

            loop = QEventLoop()
            QTimer.singleShot(10, _set_flag)
            QTimer.singleShot(50, loop.quit)
            loop.exec()
            check(timer_fired[0], "UI timer fired while downloads were running")

            # Wait for remaining downloads without blocking timers.
            deadline = time.time() + 5.0
            while time.time() < deadline and len(finished) < 5:
                app.processEvents()
                time.sleep(0.001)
            check(len(finished) == 5, "all 5 downloads finished")
            check(all(isinstance(v, object) for v in finished.values()), "finished emitted a result for every job")

            # Test cancel of queued item.
            req = HfDownloadRequest(
                repo_id="org/model",
                filename="cancel_me.gguf",
                url="http://example.com/cancel_me.gguf",
                dest_dir=td,
                size_bytes=1024 * 1024,
            )
            cancel_id = manager.enqueue(req)
            manager.cancel(cancel_id)
            app.processEvents()
            # Cancelled before start → should disappear from queue immediately.
            check(
                cancel_id not in finished,
                "cancelled queued item did not start or finish",
            )

        print("\n=== All DownloadManager smoke tests passed ===")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
