from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QTextBrowser, QTextEdit, QVBoxLayout, QWidget

from llama_data import ConfigStore, LibraryStore, LocalModel, default_paths
from ..services.download_service import (
    DownloadCancelled,
    DownloadError,
    DownloadManager,
    DownloadProgress,
    DownloadStatus,
    HfDownloadRequest,
)
from ..services.hugging_face import HfFilter, HfRepoSummary, HuggingFaceSearchService, compute_hardware_fit
from ..widgets.buttons import FilterPill, SuccessButton
from ..widgets.cards import Card, CardTitle, DownloadRow
from .base import PageBase


def _size(size: int | None) -> str:
    if not size:
        return "—"
    value = float(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:.1f} {units[idx]}" if idx else f"{int(value)} B"


# ---------------------------------------------------------------------------
# Split-set grouping
# ---------------------------------------------------------------------------

_SPLIT_SEQ_RE = re.compile(r"-\d{5}-of-\d{5}(?=\.gguf$)", re.IGNORECASE)
_SPLIT_PART_RE = re.compile(r"\.part\d+(?=\.gguf$)", re.IGNORECASE)


def _split_base(name: str) -> str | None:
    """Return the canonical base name for a split file, or None if not split."""
    if _SPLIT_SEQ_RE.search(name):
        return _SPLIT_SEQ_RE.sub("", name)
    if _SPLIT_PART_RE.search(name):
        return _SPLIT_PART_RE.sub("", name)
    return None


@dataclass(frozen=True)
class _Selectable:
    """One user-facing entry in the file combo: either a single file or a grouped split set."""
    indices: tuple[int, ...]  # indices into repo.files
    label: str
    is_split_set: bool
    total_size: int
    quant: str | None
    part_count: int = 1


def _build_selectable(repo: HfRepoSummary) -> list[_Selectable]:
    """Group repo files into selectable entries.

    Non-split files appear individually. Split files sharing the same base
    name are collapsed into one entry showing the total size and part count.
    """
    candidates = [
        (idx, f) for idx, f in enumerate(repo.files)
        if f.download_url and not f.is_multimodal_projector
    ]
    mmproj_indices = tuple(idx for idx, f in enumerate(repo.files) if f.download_url and f.is_multimodal_projector)

    # Bucket splits by base name, keeping insertion order.
    singles: list[tuple[int, HfFile]] = []
    split_buckets: dict[str, list[tuple[int, HfFile]]] = {}
    split_order: list[str] = []

    for idx, f in candidates:
        base = _split_base(f.name) if f.is_split else None
        if base is not None:
            if base not in split_buckets:
                split_buckets[base] = []
                split_order.append(base)
            split_buckets[base].append((idx, f))
        else:
            singles.append((idx, f))

    out: list[_Selectable] = []

    # Emit singles first.
    for idx, f in singles:
        label = f"{f.quantization or '?'} · {_size(f.size_bytes)} · {Path(f.name).name}"
        out.append(_Selectable(
            indices=(idx, *mmproj_indices),
            label=label,
            is_split_set=False,
            total_size=f.size_bytes or 0,
            quant=f.quantization,
        ))

    # Emit grouped split sets.
    for base in split_order:
        parts = split_buckets[base]
        total = sum(f.size_bytes or 0 for _, f in parts)
        quants = {f.quantization for _, f in parts if f.quantization}
        quant = quants.pop() if len(quants) == 1 else None
        part_count = len(parts)
        label = (
            f"{quant or '?'} · {_size(total)} · "
            f"split-set ({part_count} parts) · {Path(base).name}.gguf"
        )
        out.append(_Selectable(
            indices=tuple(idx for idx, _ in parts) + mmproj_indices,
            label=label,
            is_split_set=True,
            total_size=total,
            quant=quant,
            part_count=part_count,
        ))

    return out


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


class _SearchThread(QThread):
    finished = Signal(object)

    def __init__(self, query: str, filters: list[HfFilter], token: str | None, parent=None):
        super().__init__(parent)
        self.query = query
        self.filters = filters
        self.token = token

    def run(self) -> None:
        self.finished.emit(HuggingFaceSearchService(token=self.token).search(self.query, self.filters))


class _CardThread(QThread):
    finished = Signal(str)

    def __init__(self, repo_id: str, token: str | None, parent=None):
        super().__init__(parent)
        self.repo_id = repo_id
        self.token = token

    def run(self) -> None:
        text = HuggingFaceSearchService(token=self.token).fetch_card_text(self.repo_id) or ""
        self.finished.emit(text)



class DiscoverPage(PageBase):
    navigate_requested = Signal(str)

    def __init__(self, config_store: ConfigStore | None = None, parent=None):
        self.config_store = config_store or ConfigStore.default()
        self._repos: list[HfRepoSummary] = []
        self._selected_repo: HfRepoSummary | None = None
        self._selectable: list[_Selectable] = []
        self._threads: list[QThread] = []
        self._card_text = ""
        self._rows_by_id: dict[str, DownloadRow] = {}
        self._pending_navigate = False

        # Created before super().__init__ because PageBase calls ``build()``
        # from inside __init__, and ``build()`` needs the manager available.
        # We cannot pass ``parent=self`` yet because ``self`` is not a
        # valid QObject until PageBase's __init__ runs, so we reparent
        # the manager after super().__init__ completes.
        self._download_manager = DownloadManager(LibraryStore.default())
        super().__init__(parent)
        self._download_manager.setParent(self)

    def build(self) -> None:
        self.setProperty("subtitle", "HuggingFace GGUF discovery, explicit file selection, and download queue.")
        search_card = Card(self._body)
        layout = QVBoxLayout(search_card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Search HuggingFace", search_card))
        row = QHBoxLayout()
        self.query = QLineEdit(search_card)
        self.query.setPlaceholderText("qwen, gemma, llama...")
        self.search_button = SuccessButton("Search", search_card)
        self.search_button.setMaximumWidth(120)
        self.search_button.clicked.connect(self._search)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)

        chips = QHBoxLayout()
        self.filter_pills: dict[str, FilterPill] = {}
        for key, text, checked in (("gguf", "GGUF", True), ("gated", "Gated", False), ("multimodal", "Multimodal", False)):
            pill = FilterPill(text, search_card)
            pill.setChecked(checked)
            self.filter_pills[key] = pill
            chips.addWidget(pill)
        chips.addStretch(1)
        layout.addLayout(chips)

        self.status = QLabel("Enter a query to search HuggingFace GGUF models.", search_card)
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.results = QTableWidget(0, 7, search_card)
        self.results.setHorizontalHeaderLabels(["Repo", "Author", "Downloads", "Likes", "Best fit", "Files", "Smallest"])
        header = self.results.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.results.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.results.itemSelectionChanged.connect(self._select_repo)
        layout.addWidget(self.results)
        self._layout.addWidget(search_card)

        detail = Card(self._body)
        d = QVBoxLayout(detail)
        d.setContentsMargins(16, 14, 16, 14)
        d.setSpacing(8)
        d.addWidget(CardTitle("Selected model", detail))

        self.repo_meta = QLabel("Select a search result.", detail)
        self.repo_meta.setObjectName("Muted")
        self.repo_meta.setWordWrap(True)
        d.addWidget(self.repo_meta)

        file_row = QHBoxLayout()
        self.file_combo = QComboBox(detail)
        self.file_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.file_combo.setMinimumContentsLength(18)
        self.file_combo.view().setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.file_combo.currentIndexChanged.connect(self._on_file_changed)
        file_row.addWidget(self.file_combo, 1)
        self.download_button = SuccessButton("Download selected file", detail)
        self.download_button.setMaximumWidth(220)
        self.download_button.clicked.connect(self._download_selected)
        self.download_button.setEnabled(False)
        file_row.addWidget(self.download_button)
        d.addLayout(file_row)

        self.split_warning = QLabel(detail)
        self.split_warning.setObjectName("Muted")
        self.split_warning.setWordWrap(True)
        self.split_warning.hide()
        d.addWidget(self.split_warning)
        self.card_view = QTextBrowser(detail)
        self.card_view.setOpenExternalLinks(True)
        self.card_view.setPlainText("No model card loaded.")
        self.card_view.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.card_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.card_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.card_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.card_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        d.addWidget(self.card_view)
        self._layout.addWidget(detail)

        queue = Card(self._body)
        q = QVBoxLayout(queue)
        q.setContentsMargins(16, 14, 16, 14)
        q.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.addWidget(CardTitle("Download queue", queue))
        header_row.addStretch(1)
        self.queue_status = QLabel("0 active · 0 pending", queue)
        self.queue_status.setObjectName("Muted")
        header_row.addWidget(self.queue_status)
        q.addLayout(header_row)
        self.queue_rows: list[DownloadRow] = []
        self.queue_list = QWidget(queue)
        self.queue_list_layout = QVBoxLayout(self.queue_list)
        self.queue_list_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_list_layout.setSpacing(6)
        self.queue_list_layout.addStretch(1)
        self.queue_empty = QLabel("No active downloads.", queue)
        self.queue_empty.setObjectName("Muted")
        q.addWidget(self.queue_empty)
        q.addWidget(self.queue_list)
        self._layout.addWidget(queue)

        # Wire manager signals.
        self._download_manager.progress.connect(self._on_manager_progress)
        self._download_manager.status_changed.connect(self._on_manager_status)
        self._download_manager.finished.connect(self._on_manager_finished)
        self._download_manager.queue_changed.connect(self._on_queue_changed)

    # -- helpers ---------------------------------------------------------------

    def _resolve_token(self, config=None) -> str | None:
        import os
        env = os.environ.get("HF_TOKEN")
        if env:
            return env
        config = config or self.config_store.load()
        source = config.hf_token_source
        return source.token if source.kind == "saved" and source.token else None

    def _token(self) -> str | None:
        return self._resolve_token()

    def _active_filters(self) -> list[HfFilter]:
        return [HfFilter(key=k, label=p.text(), values=["true"]) for k, p in self.filter_pills.items() if p.isChecked()]

    # -- search ----------------------------------------------------------------

    def _search(self) -> None:
        query = self.query.text().strip()
        if not query:
            self.status.setText("Enter a model query first.")
            return
        self.search_button.setEnabled(False)
        self.status.setText(f"Searching HuggingFace for '{query}'...")
        thread = _SearchThread(query, self._active_filters(), self._token(), self)
        thread.finished.connect(self._show_results, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        self._threads.append(thread)
        thread.start()

    @Slot(object)
    def _show_results(self, outcome) -> None:
        self.search_button.setEnabled(True)
        self._repos = []
        self._selected_repo = None
        self._selectable = []
        self.file_combo.clear()
        self.card_view.setPlainText("No model card loaded.")
        if outcome.status != "ok":
            self.status.setText(outcome.message or outcome.status)
            return
        self._repos = list(outcome.repos)
        self.results.setRowCount(len(self._repos))
        for row, repo in enumerate(self._repos):
            sizes = [f.size_bytes for f in repo.files if f.size_bytes]
            smallest = _size(min(sizes)) if sizes else "—"
            for col, value in enumerate([repo.repo_id, repo.author, str(repo.downloads), str(repo.likes), repo.hardware_fit or "—", str(len(repo.files)), smallest]):
                self.results.setItem(row, col, QTableWidgetItem(value))
        self.status.setText(f"Found {len(self._repos)} GGUF repos.")
        if self._repos:
            self.results.selectRow(0)

    # -- repo selection --------------------------------------------------------

    def _select_repo(self) -> None:
        row = self.results.currentRow()
        if row < 0 or row >= len(self._repos):
            return
        repo = self._repos[row]
        self._selected_repo = repo

        self._selectable = _build_selectable(repo)
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for entry in self._selectable:
            self.file_combo.addItem(entry.label)
        self.file_combo.blockSignals(False)

        has_files = self.file_combo.count() > 0
        self.download_button.setEnabled(False)
        if has_files:
            self.file_combo.setCurrentIndex(0)
            self._on_file_changed(0)
        else:
            self.download_button.setEnabled(False)
            self.split_warning.hide()
            self._refresh_selected_fit()

        self._load_card(repo.repo_id)

    def _refresh_selected_fit(self) -> None:
        repo = self._selected_repo
        if repo is None:
            return
        selected_fit = "—"
        if self._selectable and self.file_combo.currentIndex() >= 0:
            chosen = self._selectable[self.file_combo.currentIndex()]
            selected_fit = compute_hardware_fit(chosen.total_size) or "—"
        self.repo_meta.setText(
            f"Repo: {repo.repo_id}\n"
            f"License: {repo.license or '—'}\n"
            f"Base: {repo.base_model or '—'}\n"
            f"Tags: {', '.join(repo.tags) if repo.tags else '—'}\n"
            f"Gated: {'yes' if repo.gated else 'no'}   Private: {'yes' if repo.private else 'no'}\n"
            f"Selected fit: {selected_fit}"
        )

    def _on_file_changed(self, index: int) -> None:
        """Update download button and split warning when the combo selection changes."""
        if index < 0 or index >= len(self._selectable):
            self.download_button.setEnabled(False)
            self.split_warning.hide()
            return
        self._refresh_selected_fit()
        entry = self._selectable[index]
        self.download_button.setEnabled(True)
        if entry.is_split_set:
            self.split_warning.setText(
                f"This is a {entry.part_count}-part split GGUF set ({_size(entry.total_size)} total). "
                "All parts will be downloaded together."
            )
            self.split_warning.show()
        else:
            self.split_warning.hide()

    # -- model card ------------------------------------------------------------

    def _load_card(self, repo_id: str) -> None:
        self.card_view.setPlainText("Loading model card...")
        thread = _CardThread(repo_id, self._token(), self)
        thread.finished.connect(self._show_card, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        self._threads.append(thread)
        thread.start()

    @Slot(str)
    def _show_card(self, text: str) -> None:
        self._card_text = text or ""
        if text:
            self.card_view.setMarkdown(text[:6000])
        else:
            self.card_view.setPlainText("No model card found for this repo.")

    # -- download --------------------------------------------------------------

    def _download_selected(self) -> None:
        repo = self._selected_repo
        if repo is None:
            return
        idx = self.file_combo.currentIndex()
        if idx < 0 or idx >= len(self._selectable):
            return
        entry = self._selectable[idx]
        indices = entry.indices

        config = self.config_store.load()
        base_dir = (
            Path(config.models_dir).expanduser()
            if config.models_dir
            else Path.home() / "Models" / "llamaUI"
        )
        dest_dir = base_dir / repo.repo_id.replace("/", "__")
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Build one request per individual file so the manager can run them
        # in parallel while respecting its concurrency cap.
        companion_paths = [
            str(dest_dir / Path(repo.files[i].name).name) for i in indices
        ]
        cards_dir = str(default_paths().cards_dir)
        token = self._token()

        any_queued = False
        for i in indices:
            hf_file = repo.files[i]
            label = f"{repo.repo_id}/{Path(hf_file.name).name}"
            request = HfDownloadRequest(
                repo_id=repo.repo_id,
                filename=Path(hf_file.name).name,
                url=hf_file.download_url or "",
                dest_dir=str(dest_dir),
                size_bytes=hf_file.size_bytes,
                quant=hf_file.quantization,
                architecture=repo.architecture,
                license=repo.license,
                base_model=repo.base_model,
                tags=list(repo.tags),
                gated=repo.gated,
                private=repo.private,
                card_text=self._card_text,
                companion_paths=companion_paths,
                cards_dir=cards_dir,
                hf_token=token,
            )
            job_id = self._download_manager.enqueue(request)
            any_queued = True
            row = self._add_queue_row(job_id, label)
            self._rows_by_id[job_id] = row

        if any_queued:
            self._pending_navigate = True

    def _add_queue_row(self, job_id: str, label: str) -> DownloadRow:
        self.queue_empty.hide()
        row = DownloadRow(label)
        # Insert above the trailing stretch so the row sits at the top.
        self.queue_list_layout.insertWidget(self.queue_list_layout.count() - 1, row)
        self.queue_rows.append(row)
        row.cancelled.connect(lambda _id=job_id: self._cancel_download_id(_id))
        return row

    def _cancel_download_id(self, job_id: str) -> None:
        self._download_manager.cancel(job_id)
        row = self._rows_by_id.get(job_id)
        if row is not None:
            row.set_status("cancelling…")
            row.set_cancel_enabled(False)

    @Slot(str, object)
    def _on_manager_progress(self, job_id: str, progress: DownloadProgress) -> None:
        row = self._rows_by_id.get(job_id)
        if row is None:
            return
        row.set_progress(progress.bytes_downloaded, progress.bytes_total)

    @Slot(str, str, object)
    def _on_manager_status(
        self, job_id: str, status_name: str, error: object
    ) -> None:
        row = self._rows_by_id.get(job_id)
        if row is None:
            return
        if status_name == DownloadStatus.CANCELLED.value:
            row.set_status("cancelled")
            row.set_cancel_enabled(False)
        elif status_name == DownloadStatus.FAILED.value:
            row.set_status(f"failed: {error or 'unknown'}")
            row.set_cancel_enabled(False)
        elif status_name == DownloadStatus.COMPLETED.value:
            row.set_status("done")
            row.set_cancel_enabled(False)

    @Slot(str, object)
    def _on_manager_finished(self, job_id: str, result: object) -> None:
        row = self._rows_by_id.get(job_id)
        if row is not None:
            if isinstance(result, DownloadCancelled):
                row.set_status("cancelled")
                row.set_cancel_enabled(False)
            elif isinstance(result, DownloadError):
                row.set_status(f"failed: {result}")
                row.set_cancel_enabled(False)
            else:
                row.set_status("done")
                row.set_cancel_enabled(False)
        # When the queue empties with at least one successful download,
        # navigate to the library page once so the user can see the new
        # models. Use the last finished job's path; the Library page will
        # select whatever is newest.
        if (
            self._pending_navigate
            and self._download_manager.active_count() == 0
            and isinstance(result, LocalModel)
        ):
            self._pending_navigate = False
            self.setProperty("pending_library_model_path", result.path)
            self.navigate_requested.emit("library")

    @Slot(int, int)
    def _on_queue_changed(self, active: int, pending: int) -> None:
        self.queue_status.setText(f"{active} active · {pending} pending")
        if active == 0 and pending == 0:
            self.queue_empty.show()
        else:
            self.queue_empty.hide()

