"""HTTP Client and background worker for /v1/chat/completions endpoint.

Supports text and vision (multimodal) chat completions with real-time SSE streaming.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from llama_data import ChatMessage

logger = logging.getLogger(__name__)


def encode_image_to_base64(image_path: str, max_dim: int = 1536) -> Tuple[str, str]:
    """Load an image file, resize if needed, and return (mime_type, base64_str)."""
    p = Path(image_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    mime_type, _ = mimetypes.guess_type(p)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

    # Use Pillow for image normalization and resizing
    try:
        from PIL import Image
        with Image.open(p) as img:
            # Convert RGBA to RGB for JPEG
            if img.mode in ("RGBA", "P") and mime_type == "image/jpeg":
                img = img.convert("RGB")

            # Downscale if wider/taller than max_dim to keep payload lightweight
            w, h = img.size
            if max(w, h) > max_dim:
                scale = max_dim / float(max(w, h))
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            buffer = BytesIO()
            fmt = "PNG" if mime_type == "image/png" else "JPEG"
            img.save(buffer, format=fmt, quality=85)
            b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return mime_type, b64_str
    except Exception as err:
        logger.warning("Pillow processing failed for %s, falling back to raw bytes: %s", image_path, err)
        with open(p, "rb") as fh:
            raw = fh.read()
            b64_str = base64.b64encode(raw).decode("utf-8")
            return mime_type, b64_str


def build_openai_messages(messages: List[ChatMessage], system_prompt: Optional[str] = None) -> List[Dict[str, Any]]:
    """Format ChatMessage objects into OpenAI /v1/chat/completions payload format."""
    payload_msgs: List[Dict[str, Any]] = []

    if system_prompt:
        payload_msgs.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "user" and msg.image_paths:
            content_items: List[Dict[str, Any]] = []
            if msg.content:
                content_items.append({"type": "text", "text": msg.content})

            for img_path in msg.image_paths:
                try:
                    mime, b64 = encode_image_to_base64(img_path)
                    data_uri = f"data:{mime};base64,{b64}"
                    content_items.append({
                        "type": "image_url",
                        "image_url": {"url": data_uri}
                    })
                except Exception as err:
                    logger.error("Failed to encode image %s: %s", img_path, err)

            payload_msgs.append({"role": "user", "content": content_items})
        else:
            payload_msgs.append({"role": msg.role, "content": msg.content or ""})

    return payload_msgs


class ChatStreamWorker(QThread):
    """Background worker thread that streams tokens from /v1/chat/completions."""

    token_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        endpoint_url: str,
        messages: List[ChatMessage],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.endpoint_url = endpoint_url
        self.messages = messages
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True


    def run(self) -> None:
        formatted_messages = build_openai_messages(self.messages, self.system_prompt)
        payload = {
            "messages": formatted_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if self.stream else "application/json",
            },
            method="POST",
        )

        full_text = ""
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if not self.stream:
                    raw = resp.read().decode("utf-8", errors="replace")
                    parsed = json.loads(raw)
                    choices = parsed.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        msg_obj = choices[0].get("message") or {}
                        full_text = msg_obj.get("content", "")
                        self.token_received.emit(full_text)
                    self.finished.emit(full_text)
                    return

                # Streaming SSE processing
                for line_bytes in resp:
                    if self._is_cancelled:
                        break
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_json = json.loads(data_str)
                            choices = chunk_json.get("choices") or []
                            if choices and isinstance(choices[0], dict):
                                delta = choices[0].get("delta") or {}
                                token = delta.get("content")
                                if token:
                                    full_text += token
                                    self.token_received.emit(token)
                        except json.JSONDecodeError:
                            continue

            self.finished.emit(full_text)

        except urllib.error.HTTPError as exc:
            err_text = ""
            try:
                err_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            msg = f"HTTP {exc.code}: {err_text or str(exc)}"
            logger.error("Chat API HTTP Error: %s", msg)
            self.error.emit(msg)
        except Exception as exc:
            msg = str(exc)
            logger.error("Chat API Connection Error: %s", msg)
            self.error.emit(msg)


__all__ = ["ChatStreamWorker", "build_openai_messages", "encode_image_to_base64"]
