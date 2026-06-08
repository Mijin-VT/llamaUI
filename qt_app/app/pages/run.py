from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from llama_data import ConfigStore, LibraryStore, ModelProfile, PROFILE_PRESETS, ProfileStore
from llama_data.llama_options import (
    LLAMA_OPTION_CATALOG,
    LlamaOption,
    OptionKind,
    SettingValueMap,
)

from ..services.option_schema import (
    RuntimeOption,
    RuntimeSchema,
    SchemaCache,
    build_runtime_schema,
)
from ..services.runtime import LlamaServerController, ServerState, build_argv
from ..services.runtime_api import LlamaServerApiClient
from ..widgets.buttons import DangerButton, SecondaryButton, SuccessButton
from ..widgets.cards import Card, CardTitle, FieldTile
from .base import PageBase

MAIN_OPTION_IDS = [
    "ctx_size", "cache_type_k", "cache_type_v", "no_kv_offload",
    "n_gpu_layers", "threads", "batch_size", "ubatch_size",
    "parallel", "host", "port", "temp", "top_k", "top_p", "repeat_penalty",
]

# Parser group slugs → display names for toolbox headers.
_GROUP_DISPLAY = {
    # Parser slugs → display names
    "model_loading": "Model loading",
    "performance": "Performance",
    "server_api": "Server / API",
    "sampling": "Sampling",
    "gpu_offload": "GPU / offload",
    "context_kv": "Context / KV-cache",
    "speculative": "Speculative decoding",
    "attention": "Attention",
    "debug": "Debug / logging",
    "advanced": "Advanced",
    # Catalog display names → pass through as-is
    "Model loading": "Model loading",
    "Context / KV cache": "Context / KV-cache",
    "GPU / offload": "GPU / offload",
    "Performance": "Performance",
    "Server / API": "Server / API",
    "Debug / logging": "Debug / logging",
    "Sampling": "Sampling",
    "Attention": "Attention",
    "Multimodal": "Multimodal",
    "Speculative decoding": "Speculative decoding",
    "Advanced": "Advanced",
}


def _option_label(option: LlamaOption) -> str:
    """Build a label string with default and restart metadata."""
    parts = [option.label, option.flag]
    if option.default is not None:
        parts.append(f"(default: {option.default.to_json()})")
    if option.restart_required:
        parts.append("[restart]")
    return " ".join(parts)


def _schema_option_label(rt_opt: RuntimeOption) -> str:
    """Build a label string for a non-curated schema option."""
    parts = [rt_opt.label, rt_opt.flag]
    if rt_opt.default is not None:
        parts.append(f"(default: {rt_opt.default})")
    return " ".join(parts)


def _group_display(group: str) -> str:
    return _GROUP_DISPLAY.get(group, group.replace("_", " ").title())


class RunPage(PageBase):
    inspector_changed = Signal(dict)
    def __init__(
        self,
        config_store: ConfigStore | None = None,
        library_store: LibraryStore | None = None,
        profile_store: ProfileStore | None = None,
        parent=None,
    ):
        self.config_store = config_store or ConfigStore.default()
        self.library_store = library_store or LibraryStore.default()
        self.profile_store = profile_store or ProfileStore.default()
        self.controller = LlamaServerController(on_log=None)
        self._models: list = []
        self._profiles: list = []
        self._editors: dict[str, QWidget] = {}
        self._schema: RuntimeSchema | None = None
        self._schema_options_by_id: dict[str, RuntimeOption] = {}
        self._schema_cache = SchemaCache()
        super().__init__(parent)

    def build(self) -> None:
        self.setProperty(
            "subtitle",
            "Start/stop local llama-server, edit the active profile, "
            "inspect command, health, and logs.",
        )
        self._load_schema()
        self._build_runtime_header()
        self._build_main_settings()
        self._build_advanced_groups()
        self._build_logs()
        self._reload_models()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll_status)
        self._timer.start()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _load_schema(self) -> None:
        """Load or build the runtime schema for the configured binary."""
        try:
            config = self.config_store.load()
            path = config.llama_server_path
        except Exception:
            path = None

        if not path:
            self._schema = None
            self._schema_options_by_id = {}
            return
        try:
            _probe, fresh = build_runtime_schema(path)
            cached = self._schema_cache.load(fresh.binary)
            self._schema = cached or fresh
            if cached is None:
                self._schema_cache.save(fresh)
        except Exception:
            self._schema = None

        self._schema_options_by_id = {
            opt.id: opt for opt in (self._schema.options if self._schema else [])
        }

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_runtime_header(self) -> None:
        hero = Card(self._body)
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(CardTitle("Run local llama-server", hero))

        row = QHBoxLayout()
        self.model_combo = QComboBox(hero)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.profile_combo = QComboBox(hero)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        row.addWidget(QLabel("Model", hero))
        row.addWidget(self.model_combo, 2)
        row.addWidget(QLabel("Profile", hero))
        row.addWidget(self.profile_combo, 1)
        layout.addLayout(row)

        actions = QHBoxLayout()
        save = SuccessButton("Save Profile", hero); save.clicked.connect(self._save_profile)
        save_as = SecondaryButton("Save As", hero); save_as.clicked.connect(self._save_profile_as)
        duplicate = SecondaryButton("Duplicate", hero); duplicate.clicked.connect(self._duplicate_profile)
        reset = DangerButton("Reset", hero); reset.clicked.connect(self._reset_form_to_profile)
        self.preset_combo = QComboBox(hero); self.preset_combo.addItems(["Preset…", *[p.name for p in PROFILE_PRESETS]])
        apply_preset = SecondaryButton("Apply Preset", hero); apply_preset.clicked.connect(self._apply_preset_from_combo)
        start = SuccessButton("Start", hero); start.clicked.connect(self._start)
        stop = DangerButton("Stop", hero); stop.clicked.connect(self._stop)
        restart = SecondaryButton("Restart", hero); restart.clicked.connect(self._restart)
        switch = SecondaryButton("Load via API / Restart fallback", hero); switch.clicked.connect(self._switch_model)
        for widget in (save, save_as, duplicate, reset, self.preset_combo, apply_preset, start, stop, restart, switch):
            actions.addWidget(widget)
        actions.addStretch(1)
        layout.addLayout(actions)

        stats = QHBoxLayout()
        self.state_tile = FieldTile("State", "stopped", hero)
        self.pid_tile = FieldTile("PID", "—", hero)
        self.endpoint_tile = FieldTile("Endpoint", "—", hero)
        self.profile_tile = FieldTile("Profile", "—", hero)
        for tile in (self.state_tile, self.pid_tile, self.endpoint_tile, self.profile_tile):
            stats.addWidget(tile)
        layout.addLayout(stats)

        # Schema info line
        if self._schema:
            schema_info = QLabel(
                f"Binary schema: {self._schema.parsed_count} options parsed "
                f"({self._schema.curated_supported_count} curated, "
                f"{self._schema.unknown_count} unknown) "
                f"from {self._schema.binary.path.rsplit('/', 1)[-1]}",
                hero,
            )
            schema_info.setObjectName("Muted")
            schema_info.setWordWrap(True)
            layout.addWidget(schema_info)

        self.status = QLabel("Stopped.", hero)
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.command = QPlainTextEdit(hero)
        self.command.setReadOnly(True)
        self.command.setMaximumHeight(100)
        layout.addWidget(self.command)
        self._layout.addWidget(hero)

    def _build_main_settings(self) -> None:
        card = Card(self._body)
        layout = QGridLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        row = 0
        for option_id in MAIN_OPTION_IDS:
            catalog_opt = LLAMA_OPTION_CATALOG.get(option_id)
            if catalog_opt is None:
                continue
            # When schema is loaded, only show options the binary supports
            if self._schema and option_id not in self._schema_options_by_id:
                continue

            label = QLabel(_option_label(catalog_opt), card)
            label.setToolTip(catalog_opt.help_text)
            widget = self._make_editor(catalog_opt, card)
            self._editors[option_id] = widget
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 1)
            row += 1

        self._layout.addWidget(card)

    def _build_advanced_groups(self) -> None:
        card = Card(self._body)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(CardTitle("Advanced groups", card))
        toolbox = QToolBox(card)

        handled = set(MAIN_OPTION_IDS)

        if self._schema:
            self._build_schema_advanced(toolbox, handled)
        else:
            self._build_catalog_advanced(toolbox, handled)

        layout.addWidget(toolbox)
        self._layout.addWidget(card)

    def _build_schema_advanced(self, toolbox: QToolBox, handled: set[str]) -> None:
        """Build advanced groups from the parsed runtime schema."""
        groups: dict[str, list[RuntimeOption]] = {}
        for rt_opt in self._schema.options:
            if rt_opt.id in handled:
                continue
            groups.setdefault(rt_opt.group, []).append(rt_opt)

        # Preserve catalog group order, then append any extra groups
        group_order = list(LLAMA_OPTION_CATALOG.groups_in_order())
        extra = LLAMA_OPTION_CATALOG.get("extra_args")
        if extra is not None and "extra_args" not in handled:
            box = QWidget(toolbox)
            grid = QGridLayout(box)
            grid.setContentsMargins(8, 8, 8, 8)
            label = QLabel(_option_label(extra), box)
            label.setToolTip(extra.help_text)
            widget = self._make_editor(extra, box)
            self._editors[extra.id] = widget
            grid.addWidget(label, 0, 0)
            grid.addWidget(widget, 0, 1)
            toolbox.addItem(box, "Raw extra args")
        for g in groups:
            if g not in group_order:
                group_order.append(g)

        for group_name in group_order:
            options = groups.get(group_name, [])
            if not options:
                continue
            box = QWidget(toolbox)
            grid = QGridLayout(box)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(4)
            row = 0
            for rt_opt in options:
                catalog_opt = LLAMA_OPTION_CATALOG.get(rt_opt.id)
                if catalog_opt is not None:
                    lbl = QLabel(_option_label(catalog_opt), box)
                    lbl.setToolTip(catalog_opt.help_text)
                    widget = self._make_editor(catalog_opt, box)
                else:
                    lbl = QLabel(_schema_option_label(rt_opt), box)
                    lbl.setToolTip(rt_opt.description)
                    widget = self._make_schema_editor(rt_opt, box)
                self._editors[rt_opt.id] = widget
                grid.addWidget(lbl, row, 0)
                grid.addWidget(widget, row, 1)
                row += 1
            if row > 0:
                toolbox.addItem(box, f"{_group_display(group_name)} ({row})")

    def _build_catalog_advanced(self, toolbox: QToolBox, handled: set[str]) -> None:
        """Build advanced groups from the static catalog (fallback)."""
        for group in LLAMA_OPTION_CATALOG.groups_in_order():
            box = QWidget(toolbox)
            grid = QGridLayout(box)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(4)
            row = 0
            for option in LLAMA_OPTION_CATALOG.by_group(group):
                if option.id in handled:
                    continue
                lbl = QLabel(_option_label(option), box)
                lbl.setToolTip(option.help_text)
                lbl.setWordWrap(True)
                widget = self._make_editor(option, box)
                self._editors[option.id] = widget
                grid.addWidget(lbl, row, 0)
                grid.addWidget(widget, row, 1)
                row += 1
            if row > 0:
                toolbox.addItem(box, f"{_group_display(group)} ({row})")

    def _build_logs(self) -> None:
        logs = Card(self._body)
        logs_layout = QVBoxLayout(logs)
        logs_layout.setContentsMargins(16, 14, 16, 14)
        logs_layout.setSpacing(8)
        logs_layout.addWidget(CardTitle("Server logs", logs))

        filter_row = QHBoxLayout()
        self.log_search = QLineEdit(logs)
        self.log_search.setPlaceholderText("Search logs…")
        self.log_search.textChanged.connect(self._render_logs)
        self.log_source = QComboBox(logs)
        self.log_source.addItems(["all", "stdout", "stderr"])
        self.log_source.currentIndexChanged.connect(self._render_logs)
        copy_btn = SecondaryButton("Copy", logs)
        copy_btn.clicked.connect(self._copy_logs)
        clear = SecondaryButton("Clear", logs)
        clear.clicked.connect(self._clear_logs)
        filter_row.addWidget(self.log_search, 1)
        filter_row.addWidget(self.log_source)
        filter_row.addWidget(copy_btn)
        filter_row.addWidget(clear)
        logs_layout.addLayout(filter_row)

        self.logs = QPlainTextEdit(logs)
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(10000)
        self.logs.setMaximumHeight(260)
        logs_layout.addWidget(self.logs)
        self._layout.addWidget(logs)

    # ------------------------------------------------------------------
    # Editor factories
    # ------------------------------------------------------------------

    def _make_editor(self, option: LlamaOption, parent: QWidget) -> QWidget:
        """Create a typed editor for a curated catalog option."""
        default = option.default.to_json() if option.default else None
        if option.kind is OptionKind.BOOLEAN:
            w = QCheckBox(parent)
            w.setChecked(bool(default))
            w.toggled.connect(self._update_command_preview)
            return w
        if option.kind is OptionKind.INTEGER:
            w = QSpinBox(parent)
            w.setRange(-1_000_000, 1_000_000)
            w.setValue(int(default or 0))
            w.valueChanged.connect(self._update_command_preview)
            return w
        if option.kind is OptionKind.FLOAT:
            w = QDoubleSpinBox(parent)
            w.setDecimals(3)
            w.setRange(-1000.0, 1000.0)
            w.setValue(float(default or 0.0))
            w.valueChanged.connect(self._update_command_preview)
            return w
        w = QLineEdit(parent)
        w.setText(str(default or ""))
        w.textChanged.connect(self._update_command_preview)
        return w

    def _make_schema_editor(self, rt_opt: RuntimeOption, parent: QWidget) -> QWidget:
        """Create a typed editor for a non-curated schema option."""
        default = rt_opt.default
        if rt_opt.kind == "boolean":
            w = QCheckBox(parent)
            if default is not None:
                w.setChecked(default.lower() in ("true", "1", "yes"))
            return w
        if rt_opt.kind == "integer":
            w = QSpinBox(parent)
            w.setRange(-1_000_000, 1_000_000)
            if default is not None:
                try:
                    w.setValue(int(default))
                except (ValueError, TypeError):
                    pass
            return w
        if rt_opt.kind == "float":
            w = QDoubleSpinBox(parent)
            w.setDecimals(3)
            w.setRange(-1000.0, 1000.0)
            if default is not None:
                try:
                    w.setValue(float(default))
                except (ValueError, TypeError):
                    pass
            return w
        w = QLineEdit(parent)
        if default is not None:
            w.setText(str(default))
        return w

    # ------------------------------------------------------------------
    # Editor read / write
    # ------------------------------------------------------------------

    def _editor_value(self, option: LlamaOption, widget: QWidget):
        if option.kind is OptionKind.BOOLEAN:
            return widget.isChecked()
        if option.kind is OptionKind.INTEGER:
            return int(widget.value())
        if option.kind is OptionKind.FLOAT:
            return float(widget.value())
        if option.kind is OptionKind.STRING_LIST:
            text = widget.text().strip()
            return [part for part in text.split() if part]
        return widget.text().strip() or None

    def _schema_editor_value(self, rt_opt: RuntimeOption, widget: QWidget):
        if rt_opt.kind == "boolean":
            return widget.isChecked()
        if rt_opt.kind == "integer":
            return int(widget.value())
        if rt_opt.kind == "float":
            return float(widget.value())
        return widget.text().strip() or None

    def _set_editor_value(self, option: LlamaOption, widget: QWidget, value) -> None:
        if option.kind is OptionKind.BOOLEAN:
            widget.setChecked(bool(value))
        elif option.kind is OptionKind.INTEGER:
            widget.setValue(int(value or 0))
        elif option.kind is OptionKind.FLOAT:
            widget.setValue(float(value or 0.0))
        else:
            widget.setText(str(value or ""))

    def _load_unknown_editor(
        self, option_id: str, widget: QWidget, profile: ModelProfile | None,
    ) -> None:
        """Restore an unknown-option editor from profile raw_args."""
        rt_opt = self._schema_options_by_id.get(option_id)
        if rt_opt is None or profile is None:
            return

        flag = rt_opt.flag
        args = list(profile.raw_args)
        for i, arg in enumerate(args):
            if arg != flag:
                continue
            if rt_opt.kind == "boolean":
                if isinstance(widget, QCheckBox):
                    widget.setChecked(True)
            elif i + 1 < len(args):
                val = args[i + 1]
                if rt_opt.kind == "integer" and isinstance(widget, QSpinBox):
                    try:
                        widget.setValue(int(val))
                    except (ValueError, TypeError):
                        pass
                elif rt_opt.kind == "float" and isinstance(widget, QDoubleSpinBox):
                    try:
                        widget.setValue(float(val))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(widget, QLineEdit):
                    widget.setText(val)
            return  # found the flag, done
        else:
            # Not in raw_args — restore schema default
            if rt_opt.default is not None:
                self._set_schema_editor_default(rt_opt, widget)

    def _set_schema_editor_default(self, rt_opt: RuntimeOption, widget: QWidget) -> None:
        default = rt_opt.default
        if default is None:
            return
        if rt_opt.kind == "boolean" and isinstance(widget, QCheckBox):
            widget.setChecked(default.lower() in ("true", "1", "yes"))
        elif rt_opt.kind == "integer" and isinstance(widget, QSpinBox):
            try:
                widget.setValue(int(default))
            except (ValueError, TypeError):
                pass
        elif rt_opt.kind == "float" and isinstance(widget, QDoubleSpinBox):
            try:
                widget.setValue(float(default))
            except (ValueError, TypeError):
                pass
        elif isinstance(widget, QLineEdit):
            widget.setText(str(default))

    # ------------------------------------------------------------------
    # Settings collection
    # ------------------------------------------------------------------

    def _settings_from_form(self) -> tuple[SettingValueMap, list[str]]:
        """Collect all editor values into curated settings + raw_args."""
        settings = SettingValueMap()
        raw_args: list[str] = []

        for option_id, widget in self._editors.items():
            catalog_opt = LLAMA_OPTION_CATALOG.get(option_id)
            if catalog_opt is not None:
                value = self._editor_value(catalog_opt, widget)
                settings = settings.with_value(catalog_opt, value)
            else:
                # Unknown schema option → serialize to raw_args
                rt_opt = self._schema_options_by_id.get(option_id)
                if rt_opt is None:
                    continue
                value = self._schema_editor_value(rt_opt, widget)
                if value is None:
                    continue
                if rt_opt.kind == "boolean":
                    if value:
                        raw_args.append(rt_opt.flag)
                else:
                    raw_args.extend([rt_opt.flag, str(value)])

        return settings, raw_args

    # ------------------------------------------------------------------
    # Selection state
    # ------------------------------------------------------------------

    def _selected_model(self):
        idx = self.model_combo.currentIndex()
        return self._models[idx] if 0 <= idx < len(self._models) else None

    def _selected_profile(self):
        idx = self.profile_combo.currentIndex()
        return self._profiles[idx] if 0 <= idx < len(self._profiles) else None

    def _on_model_changed(self) -> None:
        self._persist_selection()
        self._reload_profiles()

    def _on_profile_changed(self) -> None:
        self._persist_selection()
        self._load_profile_into_form()

    def _persist_selection(self) -> None:
        """Save current model/profile selection to config."""
        try:
            config = self.config_store.load()
        except Exception:
            from llama_data.models import AppConfig
            config = AppConfig()
        model = self._selected_model()
        profile = self._selected_profile()
        config.selected_model_id = model.id if model else None
        config.selected_profile_id = profile.id if profile else None
        self.config_store.save(config)

    # ------------------------------------------------------------------
    # Model / profile reload
    # ------------------------------------------------------------------

    def _reload_models(self) -> None:
        self._models = self.library_store.load()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in self._models:
            self.model_combo.addItem(model.path.rsplit("/", 1)[-1], model.id)

        # Restore selection from config
        try:
            config = self.config_store.load()
            if config.selected_model_id:
                for i, m in enumerate(self._models):
                    if m.id == config.selected_model_id:
                        self.model_combo.setCurrentIndex(i)
                        break
        except Exception:
            pass
        self.model_combo.blockSignals(False)
        self._reload_profiles()

    def _reload_profiles(self) -> None:
        model = self._selected_model()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self._profiles = self.profile_store.list_for_model(model.id) if model else []
        self._profiles.sort(key=lambda p: (not p.is_default, p.name.lower()))
        for profile in self._profiles:
            self.profile_combo.addItem(
                profile.name + (" \u2605" if profile.is_default else ""),
                profile.id,
            )
        chosen_index = 0
        try:
            config = self.config_store.load()
            if config.selected_profile_id:
                for i, p in enumerate(self._profiles):
                    if p.id == config.selected_profile_id:
                        chosen_index = i
                        break
            else:
                for i, p in enumerate(self._profiles):
                    if p.is_default:
                        chosen_index = i
                        break
        except Exception:
            pass
        if self._profiles:
            self.profile_combo.setCurrentIndex(chosen_index)
        self.profile_combo.blockSignals(False)
        self._load_profile_into_form()

    def _load_profile_into_form(self) -> None:
        profile = self._selected_profile()
        for option_id, widget in self._editors.items():
            catalog_opt = LLAMA_OPTION_CATALOG.get(option_id)
            if catalog_opt is not None:
                value = (
                    profile.settings.get(option_id).to_json()
                    if profile and profile.settings.get(option_id)
                    else (catalog_opt.default.to_json() if catalog_opt.default else None)
                )
                self._set_editor_value(catalog_opt, widget, value)
            else:
                self._load_unknown_editor(option_id, widget, profile)
        self._update_command_preview()

    def _effective_host_port(self) -> tuple[str, int]:
        config = self.config_store.load()
        host = config.host
        port = config.port
        host_widget = self._editors.get("host")
        port_widget = self._editors.get("port")
        if host_widget is not None:
            host = str(self._editor_value(LLAMA_OPTION_CATALOG.get("host"), host_widget) or host)
        if port_widget is not None:
            port = int(self._editor_value(LLAMA_OPTION_CATALOG.get("port"), port_widget) or port)
        return host, port

    # ------------------------------------------------------------------
    # Profile save
    # ------------------------------------------------------------------

    def _save_profile(self) -> None:
        model = self._selected_model()
        profile = self._selected_profile()
        if not model:
            self.status.setText("Select a model first.")
            return
        if profile is None:
            import uuid
            profile = ModelProfile(id=str(uuid.uuid4()), model_id=model.id, name="Run profile")
        settings, raw_args = self._settings_from_form()
        profile.settings = settings
        profile.raw_args = raw_args
        self.profile_store.upsert(profile)
        cfg = self.config_store.load()
        cfg.selected_profile_id = profile.id
        self.config_store.save(cfg)
        self._reload_profiles()
        self.status.setText("Profile saved from Run page.")
        self._update_command_preview()


    def _save_profile_as(self) -> None:
        model = self._selected_model()
        if not model:
            self.status.setText("Select a model first.")
            return
        import uuid
        profile = ModelProfile(id=str(uuid.uuid4()), model_id=model.id, name="Run profile copy")
        settings, raw_args = self._settings_from_form()
        profile.settings = settings
        profile.raw_args = raw_args
        self.profile_store.upsert(profile)
        cfg = self.config_store.load()
        cfg.selected_profile_id = profile.id
        self.config_store.save(cfg)
        self._reload_profiles()
        self.status.setText("Profile saved as new copy.")

    def _duplicate_profile(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self._save_profile_as()
            return
        import uuid
        dup = ModelProfile(id=str(uuid.uuid4()), model_id=profile.model_id, name=f"{profile.name} copy", settings=profile.settings.copy(), raw_args=list(profile.raw_args), preset_origin=profile.preset_origin, schema_version=profile.schema_version)
        self.profile_store.upsert(dup)
        cfg = self.config_store.load()
        cfg.selected_profile_id = dup.id
        self.config_store.save(cfg)
        self._reload_profiles()
        self.status.setText("Profile duplicated.")

    def _reset_form_to_profile(self) -> None:
        self._load_profile_into_form()
        self.status.setText("Run editor reset to saved/default values.")

    def _apply_preset_from_combo(self) -> None:
        name = self.preset_combo.currentText()
        preset = next((p for p in PROFILE_PRESETS if p.name == name), None)
        if preset is None:
            self.status.setText("Choose a preset first.")
            return
        from llama_data.llama_options import apply_preset_to_settings
        settings = apply_preset_to_settings(preset)
        for option_id, widget in self._editors.items():
            option = LLAMA_OPTION_CATALOG.get(option_id)
            if option is None:
                continue
            value = settings.get(option_id)
            if value is not None:
                self._set_editor_value(option, widget, value.to_json())
        self.status.setText(f"Applied preset: {name}.")
        self._update_command_preview()
    # ------------------------------------------------------------------
    # Argv / command preview
    # ------------------------------------------------------------------

    def _argv(self) -> list[str]:
        config = self.config_store.load()
        model = self._selected_model()
        profile = self._selected_profile()
        if model is None:
            raise RuntimeError("No model selected. Add a model in Library first.")
        if profile is not None:
            settings, raw_args = self._settings_from_form()
            profile.settings = settings
            profile.raw_args = raw_args
        else:
            settings, raw_args = self._settings_from_form()
            profile = ModelProfile(id="__ephemeral__", model_id=model.id, name="Unsaved", settings=settings, raw_args=raw_args)
        return build_argv(config, model, profile)

    def _update_command_preview(self) -> None:
        try:
            self.command.setPlainText(" ".join(self._argv()))
        except Exception as exc:
            self.command.setPlainText(str(exc))

    # ------------------------------------------------------------------
    # Server control
    # ------------------------------------------------------------------

    def _start(self) -> None:
        try:
            config = self.config_store.load()
            model = self._selected_model()
            profile = self._selected_profile()
            host, port = self._effective_host_port()
            status = self.controller.start(
                self._argv(),
                host,
                port,
                model_path=model.path if model else None,
                profile_name=profile.name if profile else None,
            )
            if model is not None:
                from llama_data.models import utc_now
                model.last_used_at = utc_now()
                self.library_store.upsert(model)
            if profile is not None:
                profile.last_used_at = model.last_used_at if model is not None else None
                self.profile_store.upsert(profile)
            self._set_status(status)
        except Exception as exc:
            self.status.setText(f"Start failed: {exc}")

    def _stop(self) -> None:
        try:
            self._set_status(self.controller.stop())
        except Exception as exc:
            self.status.setText(f"Stop failed: {exc}")

    def _restart(self) -> None:
        try:
            model = self._selected_model()
            profile = self._selected_profile()
            host, port = self._effective_host_port()
            self._set_status(
                self.controller.restart(
                    self._argv(),
                    host,
                    port,
                    model_path=model.path if model else None,
                    profile_name=profile.name if profile else None,
                )
            )
        except Exception as exc:
            self.status.setText(f"Restart failed: {exc}")

    def _switch_model(self) -> None:
        state = self.controller.status.state
        if state not in {ServerState.RUNNING, ServerState.HEALTHY, ServerState.UNHEALTHY}:
            self.status.setText("Server is not running. Start or Restart instead.")
            return
        host, port = self._effective_host_port()
        model = self._selected_model()
        if not model:
            self.status.setText("No model selected.")
            return
        result = LlamaServerApiClient(host, port).switch_model(model.path)
        if result.restart_required:
            self.status.setText(result.message + " Restarting local process.")
            self._restart()
        else:
            self.controller.note_model_switched(model.path, self._selected_profile().name if self._selected_profile() else None)
            self.status.setText(result.message)

    # ------------------------------------------------------------------
    # Polling / logs
    # ------------------------------------------------------------------

    def _poll_status(self) -> None:
        status = self.controller.status
        if status.state in {ServerState.RUNNING, ServerState.HEALTHY, ServerState.UNHEALTHY}:
            self.controller.poll_health()
            status = self.controller.status
        self._set_status(status)
        self._render_logs()
        self.inspector_changed.emit({
            "title": "Run",
            "chip_text": status.state.value,
            "chip_style": "success" if status.state in {ServerState.HEALTHY, ServerState.RUNNING} else ("warning" if status.state == ServerState.UNHEALTHY else "muted"),
            "line1": status.model_path or "No model selected",
            "line2": f"profile={status.profile_name or '—'} endpoint=http://{status.host}:{status.port}",
            "command_lines": self.command.toPlainText().splitlines()[:4] or ["No command preview available here."],
        })

    def _set_status(self, status) -> None:
        self.state_tile.set_value(status.state.value)
        self.pid_tile.set_value(str(status.pid or "\u2014"))
        self.endpoint_tile.set_value(f"http://{status.host}:{status.port}")
        self.profile_tile.set_value(status.profile_name or "\u2014")
        health = status.api_status.health if status.api_status else "—"
        capability = "api-load=yes" if status.api_status and status.api_status.model_load_supported else "api-load=no"
        slots = status.api_status.total_slots if status.api_status and status.api_status.total_slots is not None else "—"
        self.status.setText(
            f"model={status.model_path or '—'} health={health} {capability} slots={slots} last_error={status.last_error or '—'}"
        )

    def _render_logs(self) -> None:
        query = self.log_search.text().strip().lower()
        source = self.log_source.currentText()
        lines = self.controller.log_buffer.lines()
        rendered: list[str] = []
        for line in lines:
            if source != "all" and line.source != source:
                continue
            if query and query not in line.text.lower():
                continue
            rendered.append(f"{line.timestamp} [{line.source}] {line.text}")
        self.logs.setPlainText("\n".join(rendered[-1000:]))

    def _copy_logs(self) -> None:
        text = self.logs.toPlainText()
        if text:
            self.logs.copy()

    def _clear_logs(self) -> None:
        self.controller.log_buffer.clear()
        self.logs.clear()


__all__ = ["RunPage"]
