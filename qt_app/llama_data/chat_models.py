"""Dataclasses for chat messages, sessions, and system prompt templates."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional

from .models import utc_now


@dataclass
class ChatMessage:
    id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    image_paths: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "image_paths": list(self.image_paths),
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, data: Any) -> "ChatMessage":
        if not isinstance(data, dict):
            raise ValueError("Invalid ChatMessage json")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            role=str(data.get("role") or "user"),
            content=str(data.get("content") or ""),
            image_paths=list(data.get("image_paths") or []),
            created_at=str(data.get("created_at") or utc_now()),
        )


@dataclass
class ChatSession:
    id: str
    title: str
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = 0.7
    max_tokens: int = 2048
    model_alias: Optional[str] = None
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "model_alias": self.model_alias,
            "messages": [m.to_json() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json(cls, data: Any) -> "ChatSession":
        if not isinstance(data, dict):
            raise ValueError("Invalid ChatSession json")
        raw_msgs = data.get("messages") or []
        msgs = [ChatMessage.from_json(m) for m in raw_msgs if isinstance(m, dict)]
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            title=str(data.get("title") or "New Chat"),
            system_prompt=str(data.get("system_prompt") or "You are a helpful AI assistant."),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 2048)),
            model_alias=data.get("model_alias") if isinstance(data.get("model_alias"), str) else None,
            messages=msgs,
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
        )


@dataclass
class SystemPromptTemplate:
    id: str
    name: str
    prompt: str
    is_builtin: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "is_builtin": self.is_builtin,
        }

    @classmethod
    def from_json(cls, data: Any) -> "SystemPromptTemplate":
        if not isinstance(data, dict):
            raise ValueError("Invalid SystemPromptTemplate json")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or "Custom Prompt"),
            prompt=str(data.get("prompt") or ""),
            is_builtin=bool(data.get("is_builtin", False)),
        )


__all__ = ["ChatMessage", "ChatSession", "SystemPromptTemplate"]
