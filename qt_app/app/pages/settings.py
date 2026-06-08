from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from llama_data.llama_options import LLAMA_OPTION_CATALOG
from llama_data.models import AppConfig, HfTokenSource
from llama_data.stores import ConfigStore

from ..services.dialogs import pick_directory, pick_file
from ..services.option_schema import build_runtime_schema
from ..widgets.buttons import DangerButton, SecondaryButton, SuccessButton
from ..widgets.cards import Card, CardTitle, Chip
from .base import PageBase, PagePolicy


class SettingsPage(PageBase):
    """Settings page with real ConfigStore persistence."""
    policy = PagePolicy.INSPECTOR_OPTIONAL

    def __init__(self, parent=None) -> None:
        self._config_store = ConfigStore.default()
        self._config: Optional[AppConfig] = None
        self._save_feedback_timer = None
        super().__init__(parent)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> None:
        self.setProperty("subtitle", "Configure paths, connection, and Hugging Face access.")
        self._load_config()

        # --- Card 1: llama-server binary ---
        self._build_binary_card()

        # --- Card 2: Models directory ---
        self._build_models_dir_card()

        # --- Card 3: Connection settings ---
        self._build_connection_card()
        # --- Card 4: Global defaults ---
        self._build_global_defaults_card()

        # --- Card 5: Hugging Face token ---
        self._build_hf_token_card()

        # --- Card 6: Binary introspection ---
        self._build_introspection_card()

        # --- Save button row ---
        self._build_save_row()

    # ------------------------------------------------------------------
    # Card builders
    # ------------------------------------------------------------------

    def _build_binary_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("llama-server binary", card))

        row = QHBoxLayout()
        self._server_path_input = QLineEdit(card)
        self._server_path_input.setPlaceholderText("/path/to/llama-server")
        if self._config and self._config.llama_server_path:
            self._server_path_input.setText(self._config.llama_server_path)
        row.addWidget(self._server_path_input, 1)
        browse = SecondaryButton("Browse", card)
        browse.clicked.connect(self._browse_server)
        row.addWidget(browse)
        validate = SuccessButton("Validate + Parse", card)
        validate.clicked.connect(self._validate)
        row.addWidget(validate)
        layout.addLayout(row)

        self._layout.addWidget(card)

    def _build_models_dir_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Model Download Directory", card))

        row = QHBoxLayout()
        self._models_dir_input = QLineEdit(card)
        self._models_dir_input.setPlaceholderText("Directory for downloaded GGUF files")
        if self._config and self._config.models_dir:
            self._models_dir_input.setText(self._config.models_dir)
        row.addWidget(self._models_dir_input, 1)
        browse = SecondaryButton("Browse", card)
        browse.clicked.connect(self._browse_models_dir)
        row.addWidget(browse)
        layout.addLayout(row)

        self._layout.addWidget(card)

    def _build_connection_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Connection Settings", card))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        host_label = QLabel("Host", card)
        host_label.setObjectName("Muted")
        host_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(host_label, 0, 0)
        self._host_input = QLineEdit(card)
        self._host_input.setText(self._config.host if self._config else "127.0.0.1")
        self._host_input.setMaximumWidth(320)
        port_label = QLabel("Port", card)
        port_label.setObjectName("Muted")
        port_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(port_label, 1, 0)
        self._port_input = QSpinBox(card)
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(self._config.port if self._config else 8080)
        self._port_input.setMaximumWidth(320)
        grid.addWidget(self._port_input, 1, 1)

        layout.addLayout(grid)
        self._layout.addWidget(card)

    def _build_global_defaults_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Global defaults", card))
        grid = QGridLayout()
        self._global_threads = QSpinBox(card); self._global_threads.setRange(0, 1024)
        self._global_batch = QSpinBox(card); self._global_batch.setRange(0, 1_000_000)
        self._global_gpu_layers = QSpinBox(card); self._global_gpu_layers.setRange(0, 1_000_000)
        self._global_temp = QDoubleSpinBox(card); self._global_temp.setDecimals(3); self._global_temp.setRange(0.0, 10.0)
        fields = [("Threads", self._global_threads, "threads"), ("Batch size", self._global_batch, "batch_size"), ("GPU layers", self._global_gpu_layers, "n_gpu_layers"), ("Temperature", self._global_temp, "temp")]
        for row, (label, widget, option_id) in enumerate(fields):
            lbl = QLabel(label, card)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, 0)
            widget.setMaximumWidth(320)
            grid.addWidget(widget, row, 1)
            value = self._config.global_settings.get(option_id) if self._config else None
            if value is not None and value.value is not None:
                if isinstance(widget, QDoubleSpinBox): widget.setValue(float(value.value))
                else: widget.setValue(int(value.value))
        layout.addLayout(grid)
        self._layout.addWidget(card)

    def _build_hf_token_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Hugging Face Token", card))

        # Token source row
        source_row = QHBoxLayout()
        source_label = QLabel("Token source:", card)
        source_label.setObjectName("Muted")
        source_row.addWidget(source_label)

        self._token_chip = Chip("No token", "muted", card)
        source_row.addWidget(self._token_chip)
        source_row.addStretch()

        self._clear_token_btn = DangerButton("Clear", card)
        self._clear_token_btn.clicked.connect(self._clear_token)
        source_row.addWidget(self._clear_token_btn)
        layout.addLayout(source_row)

        # New token input row
        token_row = QHBoxLayout()
        self._token_input = QLineEdit(card)
        self._token_input.setPlaceholderText("hf_xxxxxxxx (optional)")
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        token_row.addWidget(self._token_input, 1)

        save_token_btn = SuccessButton("Save + Validate", card)
        save_token_btn.clicked.connect(self._save_token)
        token_row.addWidget(save_token_btn)
        layout.addLayout(token_row)

        # Feedback
        self._token_feedback = QLabel("", card)
        self._token_feedback.setObjectName("Muted")
        layout.addWidget(self._token_feedback)

        hint = QLabel(
            "A token is optional but needed for gated models or higher rate limits.\n"
            "If the HF_TOKEN environment variable is set, it is detected automatically.",
            card,
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._layout.addWidget(card)
        self._update_token_chip()

    def _build_introspection_card(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Binary Introspection", card))

        self._summary = QLabel("No binary parsed yet.", card)
        self._summary.setObjectName("Muted")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._details = QPlainTextEdit(card)
        self._details.setReadOnly(True)
        self._details.setMaximumHeight(220)
        layout.addWidget(self._details)

        self._layout.addWidget(card)

    def _build_save_row(self) -> None:
        row = QHBoxLayout()
        row.addStretch()

        self._save_feedback = QLabel("", self._body)
        self._save_feedback.setObjectName("Muted")
        row.addWidget(self._save_feedback)

        save = SuccessButton("Save Configuration", self._body)
        save.clicked.connect(self._save_config)
        row.addWidget(save)
        self._layout.addLayout(row)

    # ------------------------------------------------------------------
    # ConfigStore I/O
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """Load config from disk. Falls back to defaults on missing/invalid."""
        try:
            self._config = self._config_store.load()
        except Exception:
            self._config = AppConfig()

    def _persist_config(self, config: AppConfig) -> None:
        """Write config to disk and update local reference."""
        self._config_store.save(config)
        self._config = config

    # ------------------------------------------------------------------
    # Build a config snapshot from current form state
    # ------------------------------------------------------------------

    def _config_from_form(self, token_source: Optional[HfTokenSource] = None) -> AppConfig:
        server_path = self._server_path_input.text().strip() or None
        models_dir = self._models_dir_input.text().strip() or None
        host = self._host_input.text().strip() or "127.0.0.1"
        port = self._port_input.value()

        if token_source is None:
            token_source = self._config.hf_token_source if self._config else HfTokenSource()

        global_settings = self._config.global_settings if self._config else None
        global_settings = global_settings.copy() if global_settings is not None else SettingValueMap()
        for option_id, widget in (("threads", self._global_threads), ("batch_size", self._global_batch), ("n_gpu_layers", self._global_gpu_layers), ("temp", self._global_temp)):
            option = LLAMA_OPTION_CATALOG.get(option_id)
            if option is not None:
                value = float(widget.value()) if isinstance(widget, QDoubleSpinBox) else int(widget.value())
                global_settings = global_settings.with_value(option, value if value != 0 else None)
        return AppConfig(
            llama_server_path=server_path,
            models_dir=models_dir,
            host=host,
            port=port,
            hf_token_source=token_source,
            global_settings=global_settings,
            selected_model_id=self._config.selected_model_id if self._config else None,
            selected_profile_id=self._config.selected_profile_id if self._config else None,
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse_server(self) -> None:
        result = pick_file(self, title="Select llama-server executable", name_filter="All files (*)")
        if result.accepted and result.paths:
            self._server_path_input.setText(str(result.paths[0]))

    def _browse_models_dir(self) -> None:
        result = pick_directory(self, title="Select model download directory")
        if result.accepted and result.paths:
            self._models_dir_input.setText(str(result.paths[0]))

    def _validate(self) -> None:
        path = self._server_path_input.text().strip()
        if not path:
            self._summary.setText("Enter or browse to a llama-server binary first.")
            return
        probe, schema = build_runtime_schema(path)
        self._summary.setText(
            f"exists={probe.exists} executable={probe.is_executable} "
            f"looks_like_llama={probe.looks_like_llama_cpp} "
            f"parsed={schema.parsed_count} curated={schema.curated_supported_count} "
            f"unknown={schema.unknown_count}"
        )
        lines = [
            f"version: {probe.version or 'unknown'}",
            f"binary: {schema.binary.path}",
            "",
            "first parsed options:",
        ]
        for option in schema.options[:40]:
            marker = "curated" if option.curated else "unknown"
            lines.append(
                f"{option.flag:24} {option.kind:10} {option.group:16} {marker}  {option.description}"
            )
        self._details.setPlainText("\n".join(lines))

    def _save_config(self) -> None:
        try:
            cfg = self._config_from_form()
            self._persist_config(cfg)
            self._show_save_feedback("Configuration saved.", success=True)
        except Exception as exc:
            self._show_save_feedback(f"Save failed: {exc}", success=False)

    def _validate_token(self, token: str | None) -> str:
        from ..services.hugging_face import check_hf_connectivity
        result = check_hf_connectivity(token)
        return f"validated ({result.status_detail})" if result.reachable else f"saved, validation failed ({result.status_detail})"

    def _save_token(self) -> None:
        raw = self._token_input.text().strip()
        if not raw:
            return
        token_source = HfTokenSource(kind="saved", token=raw)
        try:
            cfg = self._config_from_form(token_source=token_source)
            self._persist_config(cfg)
            self._token_input.clear()
            self._update_token_chip()
            self._show_token_feedback(f"Token {self._validate_token(raw)}.")
        except Exception as exc:
            self._show_token_feedback(f"Failed: {exc}")

    def _clear_token(self) -> None:
        token_source = HfTokenSource(kind="none")
        try:
            cfg = self._config_from_form(token_source=token_source)
            self._persist_config(cfg)
            self._token_input.clear()
            self._update_token_chip()
            self._show_token_feedback("Token cleared.")
        except Exception as exc:
            self._show_token_feedback(f"Failed: {exc}")

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _update_token_chip(self) -> None:
        if self._config is None:
            self._token_chip.setText("No token")
            self._token_chip.set_style("muted")
            self._clear_token_btn.setVisible(False)
            return

        src = self._config.hf_token_source
        # Check env var first (same priority as Tauri resolve_hf_token)
        if os.environ.get("HF_TOKEN"):
            self._token_chip.setText("Detected HF_TOKEN env var")
            self._token_chip.set_style("success")
            self._clear_token_btn.setVisible(False)
        elif src.kind == "saved" and src.token:
            self._token_chip.setText("Saved token")
            self._token_chip.set_style("accent")
            self._clear_token_btn.setVisible(True)
        elif src.kind == "env_var":
            self._token_chip.setText("Env var (not set)")
            self._token_chip.set_style("warning")
            self._clear_token_btn.setVisible(False)
        else:
            self._token_chip.setText("No token")
            self._token_chip.set_style("muted")
            self._clear_token_btn.setVisible(False)

    def _show_token_feedback(self, msg: str) -> None:
        self._token_feedback.setText(msg)
        if self._save_feedback_timer is not None:
            self._save_feedback_timer.stop()
        from PySide6.QtCore import QTimer

        self._save_feedback_timer = QTimer(self)
        self._save_feedback_timer.setSingleShot(True)
        self._save_feedback_timer.timeout.connect(lambda: self._token_feedback.setText(""))
        self._save_feedback_timer.start(4000)

    def _show_save_feedback(self, msg: str, *, success: bool) -> None:
        self._save_feedback.setText(msg)
        self._save_feedback.setStyleSheet(
            f"color: {'#16a34a' if success else '#991b1b'};"
        )
        if self._save_feedback_timer is not None:
            self._save_feedback_timer.stop()
        from PySide6.QtCore import QTimer

        self._save_feedback_timer = QTimer(self)
        self._save_feedback_timer.setSingleShot(True)
        self._save_feedback_timer.timeout.connect(lambda: self._save_feedback.setText(""))
        self._save_feedback_timer.start(4000)
