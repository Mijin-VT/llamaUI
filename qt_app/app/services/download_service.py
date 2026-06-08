"""Download queue for HuggingFace model files.

Downloads a file from a URL to a local path using urllib (background-thread
friendly, no external deps). Tracks progress state and persists LocalModel
metadata into LibraryStore on completion.

This module is deliberately synchronous/thread-safe so callers can run it on
a background thread or wrap it with asyncio/QThread as needed.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import urllib.error
import re
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from llama_data.models import LocalModel, utc_now
from llama_data.stores import LibraryStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progress / state types
# ---------------------------------------------------------------------------


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    """Snapshot of an in-progress download."""

    url: str
    dest_path: str
    status: DownloadStatus = DownloadStatus.PENDING
    bytes_downloaded: int = 0
    bytes_total: Optional[int] = None
    error: Optional[str] = None

    @property
    def fraction(self) -> Optional[float]:
        if self.bytes_total and self.bytes_total > 0:
            return self.bytes_downloaded / self.bytes_total
        return None


# Callback signature: called with updated progress after each chunk.
ProgressCallback = Callable[[DownloadProgress], None]

# Internal chunk size for streaming download.
_CHUNK_SIZE = 64 * 1024  # 64 KiB


# ---------------------------------------------------------------------------
# DownloadError
# ---------------------------------------------------------------------------


class DownloadError(Exception):
    """Raised when a download fails for a known reason."""


# ---------------------------------------------------------------------------
# Core download function
# ---------------------------------------------------------------------------


def download_file(
    url: str,
    dest_path: str | Path,
    *,
    token: Optional[str] = None,
    expected_sha: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> DownloadProgress:
    """Download *url* to *dest_path* atomically.

    The file is written to a temp file next to the destination first, then
    renamed into place so partial downloads never corrupt the target.

    Parameters
    ----------
    url:
        Remote URL to download.
    dest_path:
        Local filesystem path for the final file.
    token:
        Optional HuggingFace bearer token for gated/private models.
    expected_sha:
        If provided, the downloaded content is verified against this hex digest
        (SHA-256). Mismatch raises :class:`DownloadError`.
    on_progress:
        Called after every chunk with an updated :class:`DownloadProgress`.
    cancel_check:
        If provided, polled before every chunk. Return ``True`` to abort.

    Returns
    -------
    DownloadProgress
        Final progress snapshot (status will be COMPLETED or CANCELLED).
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    progress = DownloadProgress(
        url=url,
        dest_path=str(dest),
        status=DownloadStatus.DOWNLOADING,
    )

    tmp_path = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resume_from = tmp_path.stat().st_size if tmp_path.exists() else 0
    if resume_from > 0 and not expected_sha:
        req.add_header("Range", f"bytes={resume_from}-")
        progress.bytes_downloaded = resume_from

    try:
        with urllib.request.urlopen(req) as resp:
            status = getattr(resp, "status", None)
            append = resume_from > 0 and status == 206 and not expected_sha
            if resume_from > 0 and not append:
                resume_from = 0
                progress.bytes_downloaded = 0
            total_raw = resp.headers.get("Content-Length")
            if total_raw is not None:
                try:
                    progress.bytes_total = int(total_raw) + (resume_from if append else 0)
                except (ValueError, TypeError):
                    pass

            sha = hashlib.sha256() if expected_sha else None

            with open(tmp_path, "ab" if append else "wb") as f:
                while True:
                    if cancel_check and cancel_check():
                        progress.status = DownloadStatus.CANCELLED
                        _notify(on_progress, progress)
                        return progress

                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    if sha:
                        sha.update(chunk)
                    progress.bytes_downloaded += len(chunk)
                    _notify(on_progress, progress)

            if cancel_check and cancel_check():
                progress.status = DownloadStatus.CANCELLED
                _notify(on_progress, progress)
                return progress

            # SHA verification
            if expected_sha and sha:
                actual = sha.hexdigest()
                if actual != expected_sha:
                    raise DownloadError(
                        f"SHA-256 mismatch: expected {expected_sha}, got {actual}"
                    )

            # Atomic move into final location.
            shutil.move(str(tmp_path), str(dest))

        progress.status = DownloadStatus.COMPLETED
        _notify(on_progress, progress)
        return progress

    except (DownloadError, urllib.error.URLError, OSError) as exc:
        progress.status = DownloadStatus.FAILED
        progress.error = str(exc)
        _notify(on_progress, progress)
        raise DownloadError(str(exc)) from exc
    finally:
        # Preserve partial downloads for resume. Only remove .part when the
        # transfer completed and the temp file should no longer exist.
        if progress.status == DownloadStatus.COMPLETED and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
                pass


def _notify(cb: Optional[ProgressCallback], progress: DownloadProgress) -> None:
    if cb is not None:
        try:
            cb(progress)
        except Exception:
            logger.debug("progress callback raised", exc_info=True)


# ---------------------------------------------------------------------------
# High-level: download + persist metadata
# ---------------------------------------------------------------------------


@dataclass
class HfDownloadRequest:
    """Everything needed to download a single HF file and register it."""

    repo_id: str
    filename: str
    url: str
    dest_dir: str  # directory (not file path) — filename is appended
    size_bytes: Optional[int] = None
    sha: Optional[str] = None
    quant: Optional[str] = None
    architecture: Optional[str] = None
    license: Optional[str] = None
    base_model: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    gated: bool = False
    private: bool = False
    card_text: Optional[str] = None
    cards_dir: Optional[str] = None
    hf_token: Optional[str] = None
    companion_paths: list[str] = field(default_factory=list)


@dataclass
class DownloadService:
    """Stateless service: download a HF file and write metadata to LibraryStore.

    Designed for background-thread usage. Call :meth:`download` with a request
    and a library store; on success the file is on disk and a :class:`LocalModel`
    entry exists.
    """

    def download(
        self,
        req: HfDownloadRequest,
        library: LibraryStore,
        *,
        on_progress: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> LocalModel:
        """Download file and persist metadata.

        Returns the :class:`LocalModel` written to *library*.

        Raises :class:`DownloadError` on failure.
        """
        dest_dir = Path(req.dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / req.filename

        # If the file already exists and matches expected size, skip download.
        if dest_path.exists() and dest_path.is_file():
            actual_size = dest_path.stat().st_size
            if req.size_bytes is None or actual_size == req.size_bytes:
                logger.info("File already exists, skipping download: %s", dest_path)
                model = _build_local_model(req, dest_path)
                library.upsert(model)
                return model

        progress = download_file(
            req.url,
            dest_path,
            token=req.hf_token,
            expected_sha=req.sha,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )

        if progress.status == DownloadStatus.CANCELLED:
            raise DownloadError("download cancelled")

        model = _build_local_model(req, dest_path)
        library.upsert(model)
        return model


def _write_card_cache(req: HfDownloadRequest) -> Optional[str]:
    if not req.card_text or not req.cards_dir:
        return None
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "__", req.repo_id)
    cards_dir = Path(req.cards_dir)
    cards_dir.mkdir(parents=True, exist_ok=True)
    path = cards_dir / f"{safe_repo}.md"
    path.write_text(req.card_text, encoding="utf-8")
    return str(path)


def _build_local_model(req: HfDownloadRequest, dest_path: Path) -> LocalModel:
    size = dest_path.stat().st_size if dest_path.exists() else req.size_bytes
    return LocalModel(
        id=str(dest_path.resolve()),
        path=str(dest_path),
        size_bytes=size,
        hf_repo=req.repo_id,
        hf_file=req.filename,
        sha=req.sha,
        quant=req.quant,
        architecture=req.architecture,
        card_cache_path=_write_card_cache(req),
        license=req.license,
        base_model=req.base_model,
        tags=list(req.tags),
        gated=req.gated,
        private=req.private,
        companion_paths=list(req.companion_paths),
    )


__all__ = [
    "DownloadError",
    "DownloadProgress",
    "DownloadService",
    "DownloadStatus",
    "HfDownloadRequest",
    "ProgressCallback",
    "download_file",
]
