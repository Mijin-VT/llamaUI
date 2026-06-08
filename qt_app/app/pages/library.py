"""Library page: shows local GGUF models from :class:`LibraryStore`.

Phase 6: table of local models with search/filter and summary tiles.
Phase 7: real directory scan, detail panel on row selection with metadata,
model card cache display, and action buttons (Run, Reveal, Open HF).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
)

from ..services.hugging_face import compute_hardware_fit
from ..services.library_scan import infer_quant, open_hf, read_card_cache, reveal_file, scan_models_dir
from ..widgets.buttons import DangerButton, SecondaryButton, SuccessButton
from ..widgets.cards import Card, CardTitle, Chip, FieldTile
from .base import PageBase


_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def _fmt_size(size_bytes: Optional[int]) -> str:
    """Render a byte count as a short human string. ``None`` -> ``"—"``."""
    if size_bytes is None or size_bytes < 0:
        return "—"
    value = float(size_bytes)
    for unit in _SIZE_UNITS:
        if value < 1024.0 or unit == _SIZE_UNITS[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def _fmt_quant(model: LocalModel) -> str:
    return (model.quant or infer_quant(model.path) or "—")


def _fmt_last_used(value: Optional[str]) -> str:
    if not value:
        return "—"
    # Persisted as ISO-8601 with timezone. Trim microseconds + tz for density.
    return value.split(".")[0].replace("T", " ")[:16]


def _fmt_path(path: str) -> str:
    home_marker = "/home/"
    if path.startswith(home_marker):
        suffix = path[len(home_marker):]
        if "/" in suffix:
            user, rest = suffix.split("/", 1)
            return f"~/{rest}"
    return path

def _fit(model: LocalModel) -> str:
    return compute_hardware_fit(model.size_bytes) or "unknown"


_TABLE_COLUMNS = (
    ("Model", 4),
    ("Path", 6),
    ("Size", 2),
    ("Quant", 2),
    ("Fit", 2),
    ("Profiles", 2),
    ("HF repo", 3),
)
_TABLE_STRETCH = tuple(stretch for _, stretch in _TABLE_COLUMNS)


class _TableHeader(QFrame):
    """One styled row acting as a column header for the model table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InsetRaised")
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setHorizontalSpacing(10)
        for col, (label, _) in enumerate(_TABLE_COLUMNS):
            cell = QLabel(label, self)
            cell.setObjectName("FieldLabel")
            layout.addWidget(cell, 0, col)
        for col, stretch in enumerate(_TABLE_STRETCH):
            layout.setColumnStretch(col, stretch)


class _TableRow(QFrame):
    """One styled row representing a single :class:`LocalModel`."""

    clicked = Signal(object)

    def __init__(self, model: LocalModel, profile_count: int, parent=None):
        super().__init__(parent)
        self._model = model
        self.setObjectName("Inset")
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        name = model.path.rsplit("/", 1)[-1] or model.id
        name_label = QLabel(name, self)
        name_label.setObjectName("Mono")
        name_label.setToolTip(model.path)
        layout.addWidget(name_label, 0, 0)

        path_label = QLabel(_fmt_path(model.path), self)
        path_label.setObjectName("Muted")
        path_label.setToolTip(model.path)
        layout.addWidget(path_label, 0, 1)

        size_label = QLabel(_fmt_size(model.size_bytes), self)
        size_label.setObjectName("Muted")
        layout.addWidget(size_label, 0, 2)

        quant_label = QLabel(_fmt_quant(model), self)
        quant_label.setObjectName("Muted")
        layout.addWidget(quant_label, 0, 3)

        fit_label = QLabel(_fit(model), self)
        fit_label.setObjectName("Muted")
        layout.addWidget(fit_label, 0, 4)

        count_label = QLabel(str(profile_count), self)
        count_label.setObjectName("Muted")
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(count_label, 0, 5)

        repo_label = QLabel(model.hf_repo or "—", self)
        repo_label.setObjectName("Muted")
        layout.addWidget(repo_label, 0, 6)

        for col, stretch in enumerate(_TABLE_STRETCH):
            layout.setColumnStretch(col, stretch)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._model)
        super().mousePressEvent(event)


class LibraryPage(PageBase):
    inspector_changed = Signal(dict)
    """Library: local GGUF inventory loaded from :class:`LibraryStore`."""

    def __init__(
        self,
        library_store: Optional[LibraryStore] = None,
        profile_store: Optional[ProfileStore] = None,
        config_store: Optional[ConfigStore] = None,
        parent=None,
    ) -> None:
        self._library_store = library_store or LibraryStore.default()
        self._profile_store = profile_store or ProfileStore.default()
        self._config_store = config_store or ConfigStore.default()
        self._selected_model: Optional[LocalModel] = None
        super().__init__(parent)

    def build(self) -> None:
        self.setProperty(
            "subtitle",
            "Local GGUF inventory, model cards, profile counts, hardware fit badges.",
        )
        self._build_header()
        self._build_table_card()
        self._build_detail_card()
        self._refresh()

    # -- UI scaffolding --------------------------------------------------

    def _build_header(self) -> None:
        header = Card(self._body)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Library", header))

        controls = QFrame(header)
        controls.setObjectName("InsetRaised")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(10, 6, 10, 6)
        controls_layout.setSpacing(8)

        self._search = QLineEdit(controls)
        self._search.setPlaceholderText("Filter by name, path, quant…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        controls_layout.addWidget(self._search, 1)

        self._rescan = SecondaryButton("Rescan", controls)
        self._rescan.setToolTip("Scan the configured models directory for GGUF files.")
        self._rescan.clicked.connect(self._on_rescan)
        controls_layout.addWidget(self._rescan)

        self._open_dir = SecondaryButton("Open models dir", controls)
        self._open_dir.setEnabled(False)
        self._open_dir.setToolTip("Configure the models directory in Settings first.")
        controls_layout.addWidget(self._open_dir)

        layout.addWidget(controls)

        tiles = QFrame(header)
        tiles_layout = QGridLayout(tiles)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        tiles_layout.setHorizontalSpacing(10)
        tiles_layout.setVerticalSpacing(10)
        self._tile_models = FieldTile("Models", "0", tiles)
        self._tile_profiles = FieldTile("Profiles", "0", tiles)
        self._tile_size = FieldTile("Total size", "—", tiles)
        self._tile_last = FieldTile("Last used", "—", tiles)
        for idx, tile in enumerate(
            (self._tile_models, self._tile_profiles, self._tile_size, self._tile_last)
        ):
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tiles_layout.addWidget(tile, 0, idx)
        layout.addWidget(tiles)
        self._layout.addWidget(header)

    def _build_detail_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(CardTitle("Model detail", card))

        self._detail_title = QLabel("Select a model to view metadata and model card.", card)
        self._detail_title.setObjectName("Muted")
        self._detail_title.setWordWrap(True)
        layout.addWidget(self._detail_title)

        self._detail_meta = QLabel("", card)
        self._detail_meta.setObjectName("Muted")
        self._detail_meta.setWordWrap(True)
        self._detail_meta.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._detail_meta)

        # Tags row — populated dynamically in _show_detail.
        self._tags_row = QHBoxLayout()
        self._tags_row.setSpacing(6)
        layout.addLayout(self._tags_row)

        # Action buttons
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._run_model = SuccessButton("Run", card)
        self._run_model.setEnabled(False)
        self._run_model.setToolTip("Set this model as the active selection for the Run page.")
        self._run_model.clicked.connect(self._on_run)
        actions.addWidget(self._run_model)

        self._edit_profiles_btn = SecondaryButton("Edit Profiles", card)
        self._edit_profiles_btn.setEnabled(False)
        self._edit_profiles_btn.setToolTip("Manage profiles for this model (navigate hook pending).")
        self._edit_profiles_btn.clicked.connect(self._on_edit_profiles)

        self._create_profile_btn = SecondaryButton("Create Profile", card)
        self._create_profile_btn.setEnabled(False)
        self._create_profile_btn.setToolTip("Create a profile for this model (navigation hook pending).")
        self._create_profile_btn.clicked.connect(self._on_create_profile)
        actions.addWidget(self._create_profile_btn)
        actions.addWidget(self._edit_profiles_btn)

        self._reveal_file = SecondaryButton("Reveal File", card)
        self._reveal_file.setEnabled(False)
        self._reveal_file.setToolTip("Open the file's parent directory in the file manager.")
        self._reveal_file.clicked.connect(self._reveal_selected)
        actions.addWidget(self._reveal_file)

        self._delete_meta_btn = DangerButton("Delete Metadata", card)
        self._delete_meta_btn.setEnabled(False)
        self._delete_meta_btn.clicked.connect(self._delete_selected_metadata)
        actions.addWidget(self._delete_meta_btn)
        self._open_hf_btn = SecondaryButton("Open HF page", card)
        self._open_hf_btn.setEnabled(False)
        self._open_hf_btn.setToolTip("Open the Hugging Face model page in your browser.")
        self._open_hf_btn.clicked.connect(self._open_selected_hf)
        actions.addWidget(self._open_hf_btn)

        actions.addStretch(1)
        layout.addLayout(actions)

        self._card_text = QTextBrowser(card)
        self._card_text.setOpenExternalLinks(True)
        self._card_text.setReadOnly(True)
        layout.addWidget(self._card_text)
        self._detail_card = card
        self._layout.addWidget(card)

    def _build_table_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(CardTitle("Local models", card))

        self._table_card = card
        self._table_layout = layout
        self._layout.addWidget(card)

    # -- detail panel ----------------------------------------------------

    def _show_detail(self, model: LocalModel) -> None:
        self._selected_model = model

        name = model.path.rsplit("/", 1)[-1] or model.id
        self._detail_title.setText(name)
        self._detail_title.setObjectName("Mono")

        # Build metadata summary
        parts = [f"<b>Path:</b> {model.path}"]
        if model.size_bytes is not None:
            parts.append(f"<b>Size:</b> {_fmt_size(model.size_bytes)}")
        if model.quant:
            parts.append(f"<b>Quant:</b> {model.quant}")
        if model.hf_repo:
            hf_ref = model.hf_repo
            if model.hf_file:
                hf_ref += f" / {model.hf_file}"
            parts.append(f"<b>HF:</b> {hf_ref}")
        if model.architecture:
            parts.append(f"<b>Arch:</b> {model.architecture}")
        if model.license:
            parts.append(f"<b>License:</b> {model.license}")
        if model.base_model:
            parts.append(f"<b>Base:</b> {model.base_model}")
        parts.append(f"<b>Fit:</b> {_fit(model)}")
        profiles = self._profile_store.list_for_model(model.id)
        if profiles:
            parts.append("<b>Profiles:</b> " + ", ".join(p.name + (" (default)" if p.is_default else "") for p in profiles))
        else:
            parts.append("<b>Profiles:</b> none")
        if model.companion_paths:
            parts.append("<b>Companion files:</b> " + ", ".join(_fmt_path(p) for p in model.companion_paths))
        self._detail_meta.setText("<br>".join(parts))

        # Tags as chips
        self._clear_tags()
        if model.tags:
            for tag in model.tags:
                chip = QLabel(tag, self._detail_card)
                chip.setObjectName("Chip")
                self._tags_row.addWidget(chip)
        self.inspector_changed.emit({
            "title": "Library",
            "chip_text": _fit(model),
            "chip_style": "success" if _fit(model) == "gpu-likely" else ("warning" if _fit(model) == "partial-gpu" else "muted"),
            "line1": name,
            "line2": model.hf_repo or _fmt_path(model.path),
            "command_lines": [f"quant={_fmt_quant(model)}", f"profiles={len(profiles)}", f"size={_fmt_size(model.size_bytes)}"],
        })

        # Show cached model card if available.
        card_md = read_card_cache(model.card_cache_path)
        if card_md:
            display = card_md[:4000]
            if len(card_md) > 4000:
                display += "\n\n… (truncated; see cached file for full card)"
            self._card_text.setMarkdown(display)
        else:
            self._card_text.setPlainText("")

        # Enable action buttons.
        self._run_model.setEnabled(True)
        self._edit_profiles_btn.setEnabled(True)
        self._reveal_file.setEnabled(Path(model.path).exists())
        self._open_hf_btn.setEnabled(bool(model.hf_repo))
        self._delete_meta_btn.setEnabled(True)
        self._create_profile_btn.setEnabled(True)

    def _reveal_selected(self) -> None:
        if self._selected_model:
            reveal_file(self._selected_model.path)

    def _open_selected_hf(self) -> None:
        if self._selected_model:
            open_hf(self._selected_model.hf_repo)

    def _clear_tags(self) -> None:
        """Remove all tag chip widgets from the tags row."""
        while self._tags_row.count():
            item = self._tags_row.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _persist_model_selection(self, model_id: str, profile_id: str | None = None) -> None:
        """Write the selected model (and optional profile) into config so other pages restore it."""
        config = self._config_store.load()
        config.selected_model_id = model_id
        if profile_id is not None:
            config.selected_profile_id = profile_id
        self._config_store.save(config)

    def _on_run(self) -> None:
        """Persist selected model and navigate to Run page."""
        m = self._selected_model
        if m:
            # Pick the default profile for this model, if any.
            default_profile = next(
                (p for p in self._profile_store.list_for_model(m.id) if p.is_default),
                None,
            )
            self._persist_model_selection(m.id, default_profile.id if default_profile else None)
            name = m.path.rsplit("/", 1)[-1] or m.id
            self._detail_title.setText(f"{name}  ✓  (selected — switching to Run)")
            self.navigate_requested.emit("run")

    def _on_edit_profiles(self) -> None:
        """Persist selected model and navigate to Profiles page."""
        m = self._selected_model
        if m:
            self._persist_model_selection(m.id)
            name = m.path.rsplit("/", 1)[-1] or m.id
            self._detail_title.setText(f"{name}  (switching to Profiles)")
            self.navigate_requested.emit("profiles")

    def _on_create_profile(self) -> None:
        """Persist selected model and navigate to Profiles page for creation."""
        m = self._selected_model
        if m:
            self._persist_model_selection(m.id)
            name = m.path.rsplit("/", 1)[-1] or m.id
            self._detail_title.setText(f"{name}  (switching to Profiles)")
            self.navigate_requested.emit("profiles")

    def select_model_by_path(self, path: str) -> None:
        for model, _count in getattr(self, "_all_models", []):
            if model.path == path:
                self._show_detail(model)
                return

    # -- data refresh ----------------------------------------------------

    def _refresh(self) -> None:
        try:
            models = list(self._library_store.load())
        except Exception as exc:  # surface, don't crash the shell
            self._render_error(f"Library store failed to load: {exc}")
            return

        profile_counts = self._profile_counts_for([m.id for m in models])

        self._all_models: list[tuple[LocalModel, int]] = list(zip(models, profile_counts))
        self._apply_filter(self._search.text())

    def _profile_counts_for(self, model_ids: Iterable[str]) -> list[int]:
        ids = set(model_ids)
        counts = {mid: 0 for mid in ids}
        try:
            for profile in self._profile_store.load():
                if profile.model_id in counts:
                    counts[profile.model_id] += 1
        except Exception:
            pass
        return [counts[mid] for mid in model_ids]

    def _delete_selected_metadata(self) -> None:
        m = self._selected_model
        if not m:
            return
        models = [model for model in self._library_store.load() if model.id != m.id]
        self._library_store.save(models)
        self._selected_model = None
        self._detail_title.setText("Metadata deleted for selected model.")
        self._detail_meta.setText("")
        self._card_text.setPlainText("")
        self._refresh()

    def _apply_filter(self, needle: str) -> None:
        needle = (needle or "").strip().lower()
        rows = self._all_models
        if needle:
            rows = [
                (model, count)
                for model, count in rows
                if needle in model.path.lower()
                or needle in (model.quant or "").lower()
                or needle in model.id.lower()
            ]
        self._render_rows(rows)

    def _render_rows(self, rows: list[tuple[LocalModel, int]]) -> None:
        self._clear_table()
        models = [m for m, _ in rows]
        counts = [c for _, c in rows]

        total_size = sum(m.size_bytes or 0 for m in models)
        last_used = max(
            (m.last_used_at for m in models if m.last_used_at),
            default=None,
        )
        self._tile_models.set_value(str(len(models)))
        self._tile_profiles.set_value(str(sum(counts)))
        self._tile_size.set_value(_fmt_size(total_size) if models else "—")
        self._tile_last.set_value(_fmt_last_used(last_used))

        if not self._all_models:
            self._render_empty()
            return
        if not rows:
            self._render_filter_empty()
            return

        grouped: dict[str, list[tuple[LocalModel, int]]] = {}
        for model, count in rows:
            key = model.hf_repo or str(Path(model.path).parent)
            grouped.setdefault(key, []).append((model, count))
        self._table_layout.addWidget(_TableHeader(self._table_card))
        for group, group_rows in sorted(grouped.items(), key=lambda item: item[0].lower()):
            group_label = QLabel(group, self._table_card)
            group_label.setObjectName("CardTitle")
            self._table_layout.addWidget(group_label)
            for model, count in group_rows:
                row = _TableRow(model, count, self._table_card)
                row.clicked.connect(self._show_detail)
                self._table_layout.addWidget(row)

    def _clear_table(self) -> None:
        # Keep the first child (CardTitle); drop everything else.
        layout = self._table_layout
        for idx in reversed(range(layout.count())):
            item = layout.takeAt(idx)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._table_layout.addWidget(CardTitle("Local models", self._table_card))

    def _render_empty(self) -> None:
        body = QLabel(
            "No local models yet. Add a GGUF via Discover, or configure the "
            "models directory in Settings and run Rescan.",
            self._table_card,
        )
        body.setObjectName("Muted")
        body.setWordWrap(True)
        self._table_layout.addWidget(body)

    def _render_filter_empty(self) -> None:
        body = QLabel(
            "No models match the current filter.",
            self._table_card,
        )
        body.setObjectName("Muted")
        body.setWordWrap(True)
        self._table_layout.addWidget(body)

    def _render_error(self, message: str) -> None:
        body = QLabel(message, self._table_card)
        body.setObjectName("Muted")
        body.setWordWrap(True)
        self._table_layout.addWidget(body)

    def _on_rescan(self) -> None:
        result = scan_models_dir(self._config_store, self._library_store)
        if result.error:
            self._rescan.setText("Error")
            self._detail_title.setText(f"Scan failed: {result.error}")
        else:
            self._rescan.setText(f"+{result.added} new")
        self._refresh()
        # Reset label after a moment.
        QTimer.singleShot(2000, lambda: self._rescan.setText("Rescan"))


__all__ = ["LibraryPage"]
