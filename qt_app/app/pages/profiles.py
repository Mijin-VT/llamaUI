"""Profiles page: per-model saved settings, grouped by model id.

Phase 5: preset application, reset, set-default, duplicate.
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from llama_data import (
    PROFILE_PRESETS,
    LLAMA_OPTION_CATALOG,
    ConfigStore,
    LibraryStore,
    LocalModel,
    ModelProfile,
    ProfileStore,
    SettingValueMap,
    apply_preset_to_settings,
    default_settings_from_catalog,
)
from ..widgets.buttons import DangerButton, SecondaryButton, SuccessButton
from ..widgets.cards import Card, CardTitle, Chip, FieldTile
from .base import PageBase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_path(path: str) -> str:
    home_marker = "/home/"
    if path.startswith(home_marker):
        suffix = path[len(home_marker):]
        if "/" in suffix:
            user, rest = suffix.split("/", 1)
            return f"~/{rest}"
    return path


def _fmt_updated(value: Optional[str]) -> str:
    if not value:
        return "—"
    return value.split(".")[0].replace("T", " ")[:16]


def _model_name(model: Optional[LocalModel]) -> str:
    if model is None:
        return "(missing model)"
    name = model.path.rsplit("/", 1)[-1]
    return name or model.id


def _settings_count(profile: ModelProfile) -> int:
    return sum(1 for _key, value in profile.settings.items() if value.is_set)


def _raw_args_count(profile: ModelProfile) -> int:
    return len(profile.raw_args or ())


# ---------------------------------------------------------------------------
# Model group card
# ---------------------------------------------------------------------------

class _ModelGroup(Card):
    """A card containing the per-model header and the list of profile rows."""

    def __init__(
        self,
        model: Optional[LocalModel],
        profiles: list[ModelProfile],
        on_select,
        parent=None,
    ):
        super().__init__(parent)
        self._model = model
        self._profiles = profiles
        self._on_select = on_select
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_row = QFrame(self)
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(10)
        title = QLabel(_model_name(self._model), title_row)
        title.setObjectName("CardTitle")
        title.setToolTip(self._model.path if self._model else "")
        title_layout.addWidget(title, 1)
        if self._model is not None:
            path_label = QLabel(_fmt_path(self._model.path), title_row)
            path_label.setObjectName("Muted")
            title_layout.addWidget(path_label)
        chip_style = "accent" if self._profiles else "muted"
        chip = Chip(
            f"{len(self._profiles)} profile" + ("s" if len(self._profiles) != 1 else ""),
            chip_style,
            title_row,
        )
        title_layout.addWidget(chip)
        layout.addWidget(title_row)

        if not self._profiles:
            empty = QLabel(
                "No saved profiles for this model. "
                "Create one from the Run page or via Save Profile As.",
                self,
            )
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return

        for profile in self._profiles:
            row = _ProfileRow(profile, self)
            row.clicked.connect(lambda pid=profile.id: self._on_select(pid))
            layout.addWidget(row)


class _ProfileRow(QFrame):
    """One dense row summarizing a single :class:`ModelProfile`."""

    from PySide6.QtCore import Signal as _Signal

    clicked = _Signal(str)

    def __init__(self, profile: ModelProfile, parent=None):
        super().__init__(parent)
        self.setObjectName("Inset")
        self.setCursor(Qt.PointingHandCursor)
        self._profile_id = profile.id
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(4)

        name_label = QLabel(profile.name, self)
        name_label.setObjectName("CardTitle")
        layout.addWidget(name_label, 0, 0)

        if profile.is_default:
            chip = Chip("default", "success", self)
        elif profile.preset_origin:
            chip = Chip("preset", "accent", self)
        else:
            chip = Chip("custom", "muted", self)
        layout.addWidget(chip, 0, 1, Qt.AlignmentFlag.AlignLeft)

        origin = QLabel(profile.preset_origin or "user", self)
        origin.setObjectName("Muted")
        layout.addWidget(origin, 0, 2, Qt.AlignmentFlag.AlignLeft)

        right = QFrame(self)
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        updated = QLabel(f"updated {_fmt_updated(profile.updated_at)}", right)
        updated.setObjectName("Muted")
        right_layout.addWidget(updated)
        counts = QLabel(
            f"{_settings_count(profile)} settings · {_raw_args_count(profile)} raw",
            right,
        )
        counts.setObjectName("Muted")
        right_layout.addWidget(counts)
        layout.addWidget(right, 0, 3, Qt.AlignmentFlag.AlignRight)

        id_label = QLabel(profile.id, self)
        id_label.setObjectName("Mono")
        layout.addWidget(id_label, 1, 0, 1, 4)

        layout.setColumnStretch(0, 4)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 3)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._profile_id)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Profile detail panel
# ---------------------------------------------------------------------------

class _ProfileDetail(Card):
    """Right-side panel showing profile metadata and action buttons."""

    def __init__(self, page: "ProfilesPage", parent=None):
        super().__init__(parent)
        self._page = page
        self._profile: Optional[ModelProfile] = None
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Header
        layout.addWidget(CardTitle("Profile detail", self))
        self._header = QLabel("Select a profile to inspect its settings.", self)
        self._header.setObjectName("Muted")
        self._header.setWordWrap(True)
        layout.addWidget(self._header)

        # Summary tiles
        tiles = QFrame(self)
        tiles_layout = QGridLayout(tiles)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        tiles_layout.setHorizontalSpacing(10)
        tiles_layout.setVerticalSpacing(10)
        self._tile_settings = FieldTile("Settings set", "—", tiles)
        self._tile_raw = FieldTile("Raw args", "—", tiles)
        self._tile_origin = FieldTile("Origin", "—", tiles)
        self._tile_updated = FieldTile("Updated", "—", tiles)
        for idx, tile in enumerate(
            (self._tile_settings, self._tile_raw, self._tile_origin, self._tile_updated)
        ):
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tiles_layout.addWidget(tile, 0, idx)
        layout.addWidget(tiles)

        # Settings preview
        self._settings_preview = QLabel("", self)
        self._settings_preview.setObjectName("Mono")
        self._settings_preview.setWordWrap(True)
        self._settings_preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._settings_preview)

        # ── Actions ────────────────────────────────────────────────────
        layout.addWidget(CardTitle("Actions", self))

        # Preset buttons
        preset_row = QFrame(self)
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(6)
        preset_label = QLabel("Apply preset:", preset_row)
        preset_label.setObjectName("Muted")
        preset_layout.addWidget(preset_label)
        for preset in PROFILE_PRESETS:
            btn = SecondaryButton(preset.name, preset_row)
            btn.setToolTip(", ".join(f"{k}={v}" for k, v in preset.values.items()))
            btn.clicked.connect(
                lambda checked=False, p=preset: self._page.apply_preset(p)
            )
            preset_layout.addWidget(btn)
        preset_layout.addStretch(1)
        layout.addWidget(preset_row)

        # Action buttons row
        actions_row = QFrame(self)
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self._btn_default = SuccessButton("Set as Default", actions_row)
        self._btn_default.setToolTip("Mark this profile as the default for its model (one per model).")
        self._btn_default.clicked.connect(self._page.set_selected_as_default)

        self._btn_duplicate = SecondaryButton("Duplicate", actions_row)
        self._btn_duplicate.clicked.connect(self._page.duplicate_selected_profile)

        self._btn_reset = DangerButton("Reset Settings", actions_row)
        self._btn_reset.setToolTip("Clear all settings and raw args from this profile.")
        self._btn_reset.clicked.connect(self._page.reset_selected_profile)

        self._btn_delete = DangerButton("Delete Profile", actions_row)
        self._btn_delete.clicked.connect(self._page.delete_selected_profile)

        actions_layout.addWidget(self._btn_default)
        actions_layout.addWidget(self._btn_duplicate)
        actions_layout.addWidget(self._btn_reset)
        actions_layout.addWidget(self._btn_delete)
        actions_layout.addStretch(1)
        layout.addWidget(actions_row)

        layout.addStretch(1)

    # -- Display --------------------------------------------------------

    def show_profile(self, profile: ModelProfile) -> None:
        self._profile = profile
        self._header.setText(f"{profile.name} — {profile.id}")
        self._tile_settings.set_value(str(_settings_count(profile)))
        self._tile_raw.set_value(str(_raw_args_count(profile)))
        self._tile_origin.set_value(profile.preset_origin or "user")
        self._tile_updated.set_value(_fmt_updated(profile.updated_at))
        self._update_default_btn_label(profile)
        self._render_settings_preview(profile)

    def show_empty(self) -> None:
        self._profile = None
        self._header.setText("Select a profile to inspect its settings.")
        self._tile_settings.set_value("—")
        self._tile_raw.set_value("—")
        self._tile_origin.set_value("—")
        self._tile_updated.set_value("—")
        self._settings_preview.setText("")
        self._btn_default.setText("Set as Default")

    def _update_default_btn_label(self, profile: ModelProfile) -> None:
        if profile.is_default:
            self._btn_default.setText("✓ Default")
        else:
            self._btn_default.setText("Set as Default")

    def _render_settings_preview(self, profile: ModelProfile) -> None:
        if not profile.settings:
            self._settings_preview.setText("(no settings)")
            return
        lines: list[str] = []
        for opt_id, value in profile.settings.items():
            option = LLAMA_OPTION_CATALOG.get(opt_id)
            if option is None:
                lines.append(f"--{opt_id} = {value}")
            else:
                lines.append(f"{option.flag} = {value}")
        self._settings_preview.setText("\n".join(lines))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class ProfilesPage(PageBase):
    """Profiles: per-model saved settings, grouped by model id."""

    def __init__(
        self,
        profile_store: Optional[ProfileStore] = None,
        library_store: Optional[LibraryStore] = None,
        config_store: Optional[ConfigStore] = None,
        parent=None,
    ) -> None:
        self._profile_store = profile_store or ProfileStore.default()
        self._library_store = library_store or LibraryStore.default()
        self._config_store = config_store or ConfigStore.default()
        self._groups_layout: Optional[QVBoxLayout] = None
        self._detail: Optional[_ProfileDetail] = None
        self._selected_profile_id: Optional[str] = None
        super().__init__(parent)

    def build(self) -> None:
        self.setProperty(
            "subtitle",
            "Per-model saved settings, presets, duplicate/reset, last-used defaults.",
        )
        self._build_summary()
        self._build_body()
        # Restore last selected profile from config.
        try:
            config = self._config_store.load()
            if config.selected_profile_id:
                self._selected_profile_id = config.selected_profile_id
        except Exception:
            pass
        self._refresh()
        try:
            cfg = self._config_store.load()
            if cfg.selected_model_id and not self._new_model_id.text().strip():
                self._new_model_id.setText(cfg.selected_model_id)
        except Exception:
            pass

    # -- UI scaffolding --------------------------------------------------

    def _build_summary(self) -> None:
        header = Card(self._body)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle("Profiles", header))

        tiles = QFrame(header)
        tiles_layout = QGridLayout(tiles)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        tiles_layout.setHorizontalSpacing(10)
        tiles_layout.setVerticalSpacing(10)
        self._tile_total = FieldTile("Profiles", "0", tiles)
        self._tile_default = FieldTile("Defaults", "0", tiles)
        self._tile_models = FieldTile("Models covered", "0", tiles)
        self._tile_orphan = FieldTile("Orphan profiles", "0", tiles)
        for idx, tile in enumerate(
            (self._tile_total, self._tile_default, self._tile_models, self._tile_orphan)
        ):
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tiles_layout.addWidget(tile, 0, idx)
        layout.addWidget(tiles)

        form = QFrame(header)
        form_layout = QHBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)
        self._new_model_id = QLineEdit(form)
        self._new_model_id.setPlaceholderText("model id or local path")
        self._new_profile_name = QLineEdit(form)
        self._new_profile_name.setPlaceholderText("profile name")
        save = SuccessButton("Save Profile", form)
        save.clicked.connect(self._save_new_profile)
        form_layout.addWidget(self._new_model_id, 2)
        form_layout.addWidget(self._new_profile_name, 1)
        form_layout.addWidget(save)
        layout.addWidget(form)
        self._layout.addWidget(header)

    def _build_body(self) -> None:
        body = QFrame(self._body)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        list_card = Card(body)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 14, 16, 14)
        list_layout.setSpacing(10)
        list_layout.addWidget(CardTitle("By model", list_card))
        self._groups_layout = list_layout
        body_layout.addWidget(list_card, 1)

        self._detail = _ProfileDetail(self, body)
        body_layout.addWidget(self._detail, 0)

        self._layout.addWidget(body)

    # -- Actions ---------------------------------------------------------

    def _save_new_profile(self) -> None:
        model_id = self._new_model_id.text().strip()
        name = self._new_profile_name.text().strip() or "Default"
        if not model_id:
            self._render_error("Enter a model id/path before saving a profile.")
            return
        profile = ModelProfile(id=str(uuid.uuid4()), model_id=model_id, name=name)
        self._profile_store.upsert(profile)
        self._new_profile_name.clear()
        self._selected_profile_id = profile.id
        self._refresh()

    def _require_selected(self) -> Optional[ModelProfile]:
        """Return the selected profile or None (and show an inline error)."""
        if not self._selected_profile_id:
            self._render_error("Select a profile first.")
            return None
        profile = self._profile_store.get(self._selected_profile_id)
        if profile is None:
            self._render_error("Selected profile no longer exists.")
            return None
        return profile

    def apply_preset(self, preset) -> None:
        """Apply a :class:`ProfilePreset` to the selected profile."""
        profile = self._require_selected()
        if profile is None:
            return
        new_settings = apply_preset_to_settings(preset)
        profile.settings = new_settings
        profile.preset_origin = preset.name
        self._profile_store.upsert(profile)
        self._refresh()

    def set_selected_as_default(self) -> None:
        """Mark the selected profile as default for its model."""
        profile = self._require_selected()
        if profile is None:
            return
        try:
            self._profile_store.set_default(profile.id)
        except LookupError:
            self._render_error("Profile disappeared before setting default.")
            return
        self._refresh()

    def duplicate_selected_profile(self) -> None:
        """Create a copy of the selected profile with a new id."""
        profile = self._require_selected()
        if profile is None:
            return
        dup = ModelProfile(
            id=str(uuid.uuid4()),
            model_id=profile.model_id,
            name=f"{profile.name} copy",
            settings=profile.settings.copy(),
            raw_args=list(profile.raw_args),
            preset_origin=profile.preset_origin,
            schema_version=profile.schema_version,
            is_default=False,
        )
        self._profile_store.upsert(dup)
        self._selected_profile_id = dup.id
        self._refresh()

    def reset_selected_profile(self) -> None:
        """Clear all settings and raw args from the selected profile."""
        profile = self._require_selected()
        if profile is None:
            return
        profile.settings = SettingValueMap()
        profile.raw_args = []
        profile.preset_origin = None
        self._profile_store.upsert(profile)
        self._refresh()

    def delete_selected_profile(self) -> None:
        """Delete the selected profile after confirmation."""
        profile = self._require_selected()
        if profile is None:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete profile")
        box.setText(f"Delete profile \"{profile.name}\"?")
        box.setInformativeText("This cannot be undone.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self._profile_store.delete(profile.id)
        self._selected_profile_id = None
        self._refresh()

    # -- Data refresh ----------------------------------------------------

    def _refresh(self) -> None:
        try:
            profiles = list(self._profile_store.load())
        except Exception as exc:
            self._render_error(f"Profile store failed to load: {exc}")
            return

        try:
            models_by_id = {m.id: m for m in self._library_store.load()}
        except Exception:
            models_by_id = {}

        groups, orphans, covered = self._group_profiles(profiles, models_by_id)

        self._tile_total.set_value(str(len(profiles)))
        self._tile_default.set_value(str(sum(1 for p in profiles if p.is_default)))
        self._tile_models.set_value(str(covered))
        self._tile_orphan.set_value(str(len(orphans)))

        self._render_groups(groups, orphans)

    def _group_profiles(
        self,
        profiles: list[ModelProfile],
        models_by_id: dict[str, LocalModel],
    ) -> tuple[list[tuple[Optional[LocalModel], list[ModelProfile]]], list[ModelProfile], int]:
        """Group profiles by model, return (known_groups, orphans, covered_count).

        ``covered_count`` is the number of distinct models that have at least
        one profile. Models present in the library but with zero profiles
        are listed as known groups with an empty profile list so the user
        sees the model exists and can target it.
        """
        by_model: dict[str, list[ModelProfile]] = {}
        for profile in profiles:
            by_model.setdefault(profile.model_id, []).append(profile)

        groups: list[tuple[Optional[LocalModel], list[ModelProfile]]] = []
        orphans: list[ModelProfile] = []

        for model_id, plist in by_model.items():
            model = models_by_id.get(model_id)
            if model is None:
                orphans.extend(plist)
            else:
                groups.append((model, plist))

        for model in models_by_id.values():
            if model.id not in by_model:
                groups.append((model, []))

        groups.sort(key=lambda pair: _model_name(pair[0]).lower())
        covered = sum(1 for _, plist in groups if plist)
        return groups, orphans, covered

    def _render_groups(
        self,
        groups: list[tuple[Optional[LocalModel], list[ModelProfile]]],
        orphans: list[ModelProfile],
    ) -> None:
        assert self._groups_layout is not None
        self._clear_groups()

        if not groups and not orphans:
            self._render_empty()
            return

        for model, plist in groups:
            self._groups_layout.addWidget(
                _ModelGroup(model, plist, self._select_profile, self._body),
            )

        if orphans:
            self._groups_layout.addWidget(_orphan_label(self._body))
            self._groups_layout.addWidget(
                _ModelGroup(None, orphans, self._select_profile, self._body),
            )

        if self._selected_profile_id is None:
            self._detail.show_empty() if self._detail else None
        else:
            self._select_profile(self._selected_profile_id)

    def _select_profile(self, profile_id: str) -> None:
        self._selected_profile_id = profile_id
        # Persist selected profile so Run page can restore it.
        config = self._config_store.load()
        config.selected_profile_id = profile_id
        profile = self._profile_store.get(profile_id)
        if profile is not None:
            config.selected_model_id = profile.model_id
        self._config_store.save(config)
        if self._detail is None:
            return
        if profile is None:
            self._detail.show_empty()
            return
        self._detail.show_profile(profile)

    def _clear_groups(self) -> None:
        assert self._groups_layout is not None
        for idx in reversed(range(self._groups_layout.count())):
            item = self._groups_layout.takeAt(idx)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _render_empty(self) -> None:
        assert self._groups_layout is not None
        body = QLabel(
            "No profiles yet. Save a profile from the Run page after "
            "tuning llama-server settings.",
            self._body,
        )
        body.setObjectName("Muted")
        body.setWordWrap(True)
        self._groups_layout.addWidget(body)

    def _render_error(self, message: str) -> None:
        assert self._groups_layout is not None
        body = QLabel(message, self._body)
        body.setObjectName("Muted")
        body.setWordWrap(True)
        self._groups_layout.addWidget(body)


def _orphan_label(parent: QWidget) -> QLabel:
    label = QLabel("Profiles referencing missing models", parent)
    label.setObjectName("CardTitle")
    return label


__all__ = ["ProfilesPage"]
