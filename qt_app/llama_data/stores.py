"""Versioned stores for config, library, and profiles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .models import AppConfig, LocalModel, ModelProfile, utc_now
from .paths import DataPaths, default_paths
from .storage import EMPTY_MIGRATIONS, MigrationChain, VersionedEnvelope, current_version, load_envelope, resolve_version, save_envelope

_CHAIN = MigrationChain(migrations=EMPTY_MIGRATIONS, target=current_version())


@dataclass
class ConfigStore:
    paths: DataPaths

    @classmethod
    def default(cls) -> "ConfigStore":
        return cls(default_paths())

    def load(self) -> AppConfig:
        envelope = load_envelope(self.paths.config_path)
        if envelope is None:
            return AppConfig()
        data = resolve_version(envelope, _CHAIN)
        return AppConfig.from_json(data)

    def save(self, config: AppConfig) -> None:
        self.paths.ensure()
        save_envelope(self.paths.config_path, VersionedEnvelope(current_version(), config.to_json()))


@dataclass
class LibraryStore:
    paths: DataPaths

    @classmethod
    def default(cls) -> "LibraryStore":
        return cls(default_paths())

    def load(self) -> list[LocalModel]:
        envelope = load_envelope(self.paths.library_path)
        if envelope is None:
            return []
        data = resolve_version(envelope, _CHAIN)
        if not isinstance(data, list):
            return []
        out: list[LocalModel] = []
        for item in data:
            try:
                out.append(LocalModel.from_json(item))
            except (TypeError, ValueError):
                continue
        return out

    def save(self, models: Iterable[LocalModel]) -> None:
        self.paths.ensure()
        payload = [m.to_json() for m in models]
        save_envelope(self.paths.library_path, VersionedEnvelope(current_version(), payload))

    def upsert(self, model: LocalModel) -> None:
        models = {m.id: m for m in self.load()}
        existing = models.get(model.id)
        if existing is not None:
            model.created_at = existing.created_at
        model.updated_at = utc_now()
        models[model.id] = model
        self.save(models.values())


@dataclass
class ProfileStore:
    paths: DataPaths

    @classmethod
    def default(cls) -> "ProfileStore":
        return cls(default_paths())

    def load(self) -> list[ModelProfile]:
        envelope = load_envelope(self.paths.profiles_path)
        if envelope is None:
            return []
        data = resolve_version(envelope, _CHAIN)
        if not isinstance(data, list):
            return []
        out: list[ModelProfile] = []
        for item in data:
            try:
                out.append(ModelProfile.from_json(item))
            except (TypeError, ValueError, KeyError):
                continue
        return out

    def save(self, profiles: Iterable[ModelProfile]) -> None:
        self.paths.ensure()
        payload = [p.to_json() for p in profiles]
        save_envelope(self.paths.profiles_path, VersionedEnvelope(current_version(), payload))

    def list_for_model(self, model_id: str) -> list[ModelProfile]:
        return [p for p in self.load() if p.model_id == model_id]

    def get(self, profile_id: str) -> Optional[ModelProfile]:
        return next((p for p in self.load() if p.id == profile_id), None)

    def upsert(self, profile: ModelProfile) -> None:
        profiles = {p.id: p for p in self.load()}
        profile.touch()
        profiles[profile.id] = profile
        self.save(profiles.values())

    def delete(self, profile_id: str) -> None:
        self.save(p for p in self.load() if p.id != profile_id)

    def set_default(self, profile_id: str) -> None:
        profiles = {p.id: p for p in self.load()}
        target = profiles.get(profile_id)
        if target is None:
            raise LookupError(f"profile {profile_id!r} not found")
        for p in profiles.values():
            if p.model_id != target.model_id:
                continue
            wants_default = p.id == profile_id
            if p.is_default != wants_default:
                p.is_default = wants_default
                p.touch()
        self.save(profiles.values())


__all__ = ["ConfigStore", "LibraryStore", "ProfileStore"]
