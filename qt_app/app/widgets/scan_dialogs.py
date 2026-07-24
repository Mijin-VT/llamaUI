"""Dialogs and worker thread for custom folder scanning in the Library page."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from llama_data import LibraryStore
from .. import theme
from ..services.library_scan import (
    CustomScanOptions,
    CustomScanProgress,
    ScanResult,
    scan_custom_folder,
)
from .buttons import DangerButton, SecondaryButton, SuccessButton
from .cards import CardTitle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker Thread
# ---------------------------------------------------------------------------

class CustomFolderScanThread(QThread):
    """Background worker thread executing custom folder scanning."""

    progress_updated = Signal(object)  # CustomScanProgress
    scan_finished = Signal(object)     # ScanResult
    scan_error = Signal(str)

    def __init__(self, options: CustomScanOptions, library_store: LibraryStore, parent=None):
        super().__init__(parent)
        self.options = options
        self.library_store = library_store
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def _check_cancelled(self) -> bool:
        return self._is_cancelled

    def _on_progress(self, progress: CustomScanProgress) -> None:
        self.progress_updated.emit(progress)

    def run(self) -> None:
        try:
            result = scan_custom_folder(
                options=self.options,
                library=self.library_store,
                progress_callback=self._on_progress,
                cancel_check=self._check_cancelled,
            )
            self.scan_finished.emit(result)
        except Exception as err:
            logger.error("Custom folder scan error: %s", err, exc_info=True)
            self.scan_error.emit(str(err))


# ---------------------------------------------------------------------------
# Options Dialog
# ---------------------------------------------------------------------------

class ScanCustomFolderOptionsDialog(QDialog):
    """Dialog to configure options for scanning a custom directory."""

    def __init__(self, initial_folder: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar escaneo de carpeta personalizada")
        self.resize(520, 360)
        self.selected_folder = initial_folder.resolve()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Header Title
        title_lbl = CardTitle("Scan Custom Folder Options", self)
        layout.addWidget(title_lbl)

        # Selected Folder Row
        folder_frame = QFrame(self)
        folder_frame.setObjectName("InsetRaised")
        folder_layout = QHBoxLayout(folder_frame)
        folder_layout.setContentsMargins(10, 6, 10, 6)
        folder_layout.setSpacing(8)

        self.folder_edit = QLineEdit(str(self.selected_folder), folder_frame)
        self.folder_edit.setReadOnly(True)
        folder_layout.addWidget(self.folder_edit, 1)

        change_btn = SecondaryButton("Cambiar carpeta...", folder_frame)
        change_btn.clicked.connect(self._change_folder)
        folder_layout.addWidget(change_btn)

        layout.addWidget(folder_frame)

        # Options Form
        form_widget = QWidget(self)
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # Checkbox Recursive
        self.recursive_chk = QCheckBox("Escanear subcarpetas (recursivo)", form_widget)
        self.recursive_chk.setChecked(True)
        form_layout.addRow("", self.recursive_chk)

        # Checkbox Hidden
        self.hidden_chk = QCheckBox("Incluir carpetas ocultas", form_widget)
        self.hidden_chk.setChecked(False)
        form_layout.addRow("", self.hidden_chk)

        # Max Depth SpinBox
        self.max_depth_spin = QSpinBox(form_widget)
        self.max_depth_spin.setRange(1, 99)
        self.max_depth_spin.setValue(12)
        form_layout.addRow("Profundidad máxima:", self.max_depth_spin)

        # Excluded Dirs LineEdit
        self.excluded_edit = QLineEdit("node_modules, .git, __pycache__, venv, env, dist", form_widget)
        form_layout.addRow("Carpetas excluidas (separadas por coma):", self.excluded_edit)

        # Min Size DoubleSpinBox
        self.min_size_spin = QDoubleSpinBox(form_widget)
        self.min_size_spin.setRange(0.0, 10000.0)
        self.min_size_spin.setValue(5.0)
        self.min_size_spin.setSingleStep(0.5)
        self.min_size_spin.setSuffix(" MB")
        form_layout.addRow("Tamaño mínimo de GGUF:", self.min_size_spin)

        layout.addWidget(form_widget)

        # Action Buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        actions_layout.addStretch(1)

        cancel_btn = SecondaryButton("Cancelar", self)
        cancel_btn.clicked.connect(self.reject)
        actions_layout.addWidget(cancel_btn)

        start_btn = SuccessButton("Iniciar escaneo", self)
        start_btn.clicked.connect(self.accept)
        actions_layout.addWidget(start_btn)

        layout.addLayout(actions_layout)

    def _change_folder(self) -> None:
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta para escanear",
            str(self.selected_folder),
        )
        if new_dir:
            self.selected_folder = Path(new_dir).resolve()
            self.folder_edit.setText(str(self.selected_folder))

    def get_options(self) -> CustomScanOptions:
        excluded_raw = self.excluded_edit.text().split(",")
        excluded_list = [e.strip() for e in excluded_raw if e.strip()]

        return CustomScanOptions(
            target_dir=self.selected_folder,
            recursive=self.recursive_chk.isChecked(),
            include_hidden=self.hidden_chk.isChecked(),
            max_depth=self.max_depth_spin.value(),
            excluded_dirs=excluded_list,
            min_size_mb=self.min_size_spin.value(),
        )


# ---------------------------------------------------------------------------
# Progress Dialog
# ---------------------------------------------------------------------------

class ScanProgressDialog(QDialog):
    """Modal dialog displaying live progress of a custom folder scan."""

    def __init__(self, options: CustomScanOptions, library_store: LibraryStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escaneando carpeta...")
        self.setFixedSize(480, 220)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.options = options
        self.library_store = library_store
        self.result: Optional[ScanResult] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        # Header
        self.title_label = CardTitle(f"Escaneando {options.target_dir.name}...", self)
        layout.addWidget(self.title_label)

        # Indeterminate / Pulse Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)  # indeterminate loading animation
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)

        # Stats Card
        stats_frame = QFrame(self)
        stats_frame.setObjectName("Inset")
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(12, 8, 12, 8)
        stats_layout.setSpacing(4)

        self.files_lbl = QLabel("Archivos escaneados: 0", stats_frame)
        self.files_lbl.setStyleSheet(f"color: {theme.FG_PRIMARY}; font-weight: 600;")
        stats_layout.addWidget(self.files_lbl)

        self.primary_lbl = QLabel("Modelos primarios encontrados: 0", stats_frame)
        self.primary_lbl.setStyleSheet(f"color: {theme.SUCCESS}; font-size: 12px;")
        stats_layout.addWidget(self.primary_lbl)

        self.companion_lbl = QLabel("Archivos companion encontrados: 0", stats_frame)
        self.companion_lbl.setStyleSheet(f"color: {theme.FG_MUTED}; font-size: 11px;")
        stats_layout.addWidget(self.companion_lbl)

        self.folder_lbl = QLabel(f"Carpeta: {options.target_dir}", stats_frame)
        self.folder_lbl.setObjectName("Muted")
        self.folder_lbl.setStyleSheet("font-size: 11px;")
        self.folder_lbl.setWordWrap(True)
        stats_layout.addWidget(self.folder_lbl)

        layout.addWidget(stats_frame)

        # Cancel Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self.cancel_btn = DangerButton("Cancelar", self)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        # Thread Setup
        self.thread = CustomFolderScanThread(options, library_store, self)
        self.thread.progress_updated.connect(self._update_progress)
        self.thread.scan_finished.connect(self._on_finished)
        self.thread.scan_error.connect(self._on_error)
        self.thread.start()

    def _update_progress(self, progress: CustomScanProgress) -> None:
        self.files_lbl.setText(f"Archivos escaneados: {progress.scanned_files}")
        self.primary_lbl.setText(f"Modelos primarios encontrados: {progress.primary_models_found}")
        self.companion_lbl.setText(f"Archivos companion encontrados: {progress.companion_files_found}")

        folder_str = progress.current_folder
        if len(folder_str) > 55:
            folder_str = "..." + folder_str[-52:]
        self.folder_lbl.setText(f"Carpeta actual: {folder_str}")

    def _on_finished(self, result: ScanResult) -> None:
        self.result = result
        self.accept()

    def _on_error(self, err_msg: str) -> None:
        self.result = ScanResult(error=err_msg)
        self.reject()

    def _cancel_scan(self) -> None:
        self.thread.cancel()
        self.cancel_btn.setText("Cancelando...")
        self.cancel_btn.setEnabled(False)
        self.thread.wait(2000)
        self.reject()


__all__ = [
    "CustomFolderScanThread",
    "ScanCustomFolderOptionsDialog",
    "ScanProgressDialog",
]
