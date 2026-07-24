"""Versioned store for chat sessions and system prompt templates."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .chat_models import ChatMessage, ChatSession, SystemPromptTemplate
from .paths import DataPaths, default_paths
from .storage import FileLock, MigrationChain, VersionedEnvelope, current_version, load_envelope, resolve_version, save_envelope

logger = logging.getLogger(__name__)

_CHAT_WRITE_LOCK = threading.RLock()
_TEMPLATE_WRITE_LOCK = threading.RLock()

_CHAT_CHAIN = MigrationChain(migrations={1: lambda payload: payload}, target=current_version())
_TEMPLATE_CHAIN = MigrationChain(migrations={1: lambda payload: payload}, target=current_version())

BUILTIN_TEMPLATES: list[SystemPromptTemplate] = [
    SystemPromptTemplate(
        id="default_assistant",
        name="Default Assistant",
        prompt="You are a helpful, respectful, and honest AI assistant. Always answer as helpfully as possible while being safe.",
        is_builtin=True,
    ),
    SystemPromptTemplate(
        id="code_helper",
        name="Code Developer",
        prompt="You are an expert software engineer. Write clean, efficient, modern, well-documented code. Explain key concepts concisely.",
        is_builtin=True,
    ),
    SystemPromptTemplate(
        id="vision_analyst",
        name="Vision & Image Analyst",
        prompt="You are a specialized multimodal AI assistant. Analyze image content in detail, describing objects, text, colors, layouts, and context accurately.",
        is_builtin=True,
    ),
    SystemPromptTemplate(
        id="creative_writer",
        name="Creative Writer",
        prompt="You are a creative writer and storyteller. Use rich vocabulary, vivid descriptions, and engaging tone.",
        is_builtin=True,
    ),
    SystemPromptTemplate(
        id="concise_summarizer",
        name="Concise Summarizer",
        prompt="You are a concise assistant. Provide direct, brief, bulleted summaries without unnecessary filler or introduction.",
        is_builtin=True,
    ),
]


@dataclass
class ChatStore:
    paths: DataPaths

    @classmethod
    def default(cls) -> "ChatStore":
        return cls(default_paths())

    # --- Chat Sessions --------------------------------------------------------

    def load_sessions(self) -> list[ChatSession]:
        with _CHAT_WRITE_LOCK:
            envelope = load_envelope(self.paths.chat_sessions_path)
            if envelope is None:
                return []
            data = resolve_version(envelope, _CHAT_CHAIN)
            if not isinstance(data, list):
                return []
            sessions: list[ChatSession] = []
            for item in data:
                try:
                    sessions.append(ChatSession.from_json(item))
                except Exception as err:
                    logger.warning("Failed to load chat session: %s", err)
                    continue
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            return sessions

    def save_sessions(self, sessions: Iterable[ChatSession]) -> None:
        with _CHAT_WRITE_LOCK:
            self.paths.ensure()
            payload = [s.to_json() for s in sessions]
            save_envelope(self.paths.chat_sessions_path, VersionedEnvelope(current_version(), payload))

    def upsert_session(self, session: ChatSession) -> None:
        with _CHAT_WRITE_LOCK, FileLock(self.paths.chat_sessions_path):
            existing = {s.id: s for s in self.load_sessions()}
            session.touch()
            existing[session.id] = session
            self.save_sessions(existing.values())

    def delete_session(self, session_id: str) -> None:
        with _CHAT_WRITE_LOCK, FileLock(self.paths.chat_sessions_path):
            sessions = [s for s in self.load_sessions() if s.id != session_id]
            self.save_sessions(sessions)

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        sessions = self.load_sessions()
        return next((s for s in sessions if s.id == session_id), None)

    # --- System Prompt Templates ----------------------------------------------

    def load_templates(self) -> list[SystemPromptTemplate]:
        with _TEMPLATE_WRITE_LOCK:
            envelope = load_envelope(self.paths.chat_templates_path)
            custom_templates: list[SystemPromptTemplate] = []
            if envelope is not None:
                data = resolve_version(envelope, _TEMPLATE_CHAIN)
                if isinstance(data, list):
                    for item in data:
                        try:
                            t = SystemPromptTemplate.from_json(item)
                            if not t.is_builtin:
                                custom_templates.append(t)
                        except Exception:
                            continue
            # Return builtins first, followed by custom templates
            return list(BUILTIN_TEMPLATES) + custom_templates

    def save_custom_templates(self, templates: Iterable[SystemPromptTemplate]) -> None:
        with _TEMPLATE_WRITE_LOCK:
            self.paths.ensure()
            custom_only = [t.to_json() for t in templates if not t.is_builtin]
            save_envelope(self.paths.chat_templates_path, VersionedEnvelope(current_version(), custom_only))

    def upsert_template(self, template: SystemPromptTemplate) -> None:
        if template.is_builtin:
            return
        with _TEMPLATE_WRITE_LOCK, FileLock(self.paths.chat_templates_path):
            all_templates = self.load_templates()
            custom = {t.id: t for t in all_templates if not t.is_builtin}
            custom[template.id] = template
            self.save_custom_templates(custom.values())

    def delete_template(self, template_id: str) -> None:
        with _TEMPLATE_WRITE_LOCK, FileLock(self.paths.chat_templates_path):
            all_templates = self.load_templates()
            custom = [t for t in all_templates if not t.is_builtin and t.id != template_id]
            self.save_custom_templates(custom)


__all__ = ["BUILTIN_TEMPLATES", "ChatStore"]
