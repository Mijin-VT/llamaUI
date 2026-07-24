"""Chat page with vision (multimodal) support, history persistence, and system prompt templates."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QPushButton,
)

from llama_data import (
    ChatMessage,
    ChatSession,
    ChatStore,
    ConfigStore,
    SystemPromptTemplate,
)
from .. import theme
from ..services.chat_service import ChatStreamWorker
from ..services.runtime_api import LlamaServerApiClient
from ..widgets.buttons import DangerButton, SecondaryButton, SuccessButton
from ..widgets.cards import Card, CardTitle, Chip
from ..widgets.slider_spin import SliderDoubleSpinBox
from .base import PageBase, PagePolicy

logger = logging.getLogger(__name__)


class _HealthCheckThread(QThread):
    status_ready = Signal(object, str, int)

    def __init__(self, host: str, port: int, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port

    def run(self) -> None:
        client = LlamaServerApiClient(host=self.host, port=self.port, timeout=0.8)
        status = client.check_health()
        self.status_ready.emit(status, self.host, self.port)



# ---------------------------------------------------------------------------
# Input Text Edit with Enter-to-Send
# ---------------------------------------------------------------------------

class ChatInputEdit(QPlainTextEdit):
    """Custom multi-line text input sending message on Enter (Shift+Enter for newline)."""

    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Type your message here... (Shift+Enter for new line)")
        self.setMinimumHeight(44)
        self.setMaximumHeight(140)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                event.accept()
                self.send_requested.emit()
                return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Chat Message Widget
# ---------------------------------------------------------------------------

class MessageBubble(QFrame):
    """Custom message bubble for user and assistant messages."""

    def __init__(self, message: ChatMessage, parent=None):
        super().__init__(parent)
        self.message = message
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header: Role badge & time
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        is_user = message.role == "user"
        role_label = QLabel("You" if is_user else "Assistant", self)
        role_label.setStyleSheet(
            f"font-weight: 700; font-size: 12px; color: {'#0ea5e9' if is_user else '#22c55e'};"
        )
        header_row.addWidget(role_label)

        time_str = message.created_at.split("T")[-1][:5] if "T" in message.created_at else ""
        if time_str:
            time_label = QLabel(time_str, self)
            time_label.setObjectName("Muted")
            time_label.setStyleSheet("font-size: 10px;")
            header_row.addWidget(time_label)

        header_row.addStretch(1)
        layout.addLayout(header_row)

        # Image previews if user attached images
        if message.image_paths:
            img_row = QHBoxLayout()
            img_row.setSpacing(8)
            img_row.setAlignment(Qt.AlignmentFlag.AlignLeft)

            for path_str in message.image_paths:
                if os.path.exists(path_str):
                    pix = QPixmap(path_str)
                    if not pix.isNull():
                        thumb = QLabel(self)
                        thumb.setPixmap(pix.scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        thumb.setStyleSheet(f"border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 2px;")
                        img_row.addWidget(thumb)
            layout.addLayout(img_row)

        # Text content
        self.text_label = QLabel(message.content, self)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.text_label.setStyleSheet(
            f"font-size: 13px; line-height: 1.4; color: {theme.FG_PRIMARY};"
        )
        layout.addWidget(self.text_label)

        # Bubble background style based on role
        if is_user:
            self.setStyleSheet(
                f"background-color: {theme.BG_RAISED}; border: 1px solid {theme.BORDER}; border-radius: 8px;"
            )
        else:
            self.setStyleSheet(
                f"background-color: {theme.BG_PANEL}; border: 1px solid {theme.BORDER_SOFT}; border-radius: 8px;"
            )

    def append_text(self, text_chunk: str) -> None:
        self.message.content += text_chunk
        self.text_label.setText(self.message.content)


# ---------------------------------------------------------------------------
# Chat Page Widget
# ---------------------------------------------------------------------------

class ChatPage(PageBase):
    """Full-page Chat interface supporting /v1/chat/completions, vision, history, & prompt templates."""

    policy = PagePolicy.FULL_WIDTH

    def __init__(self, chat_store: Optional[ChatStore] = None, config_store: Optional[ConfigStore] = None, parent=None):
        self.chat_store = chat_store or ChatStore.default()
        self.config_store = config_store or ConfigStore.default()
        self.current_session: Optional[ChatSession] = None
        self.active_worker: Optional[ChatStreamWorker] = None
        self.pending_images: List[str] = []
        super().__init__(parent)
        self.setProperty("subtitle", "Local /v1/chat/completions endpoint & vision assistant")

    def build(self) -> None:
        main_splitter = QSplitter(Qt.Orientation.Horizontal, self._body)
        main_splitter.setHandleWidth(theme.SPLITTER_HANDLE_WIDTH)

        # =====================================================================
        # LEFT PANEL: Sessions & System Prompt Settings
        # =====================================================================
        left_panel = QWidget(main_splitter)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(12)

        # New Chat Button
        new_chat_btn = SuccessButton("+ New Chat", left_panel)
        new_chat_btn.clicked.connect(self._create_new_session)
        left_layout.addWidget(new_chat_btn)

        # Sessions List Card
        sessions_card = Card(left_panel)
        sessions_card_layout = QVBoxLayout(sessions_card)
        sessions_card_layout.setContentsMargins(12, 10, 12, 10)
        sessions_card_layout.setSpacing(8)

        sessions_card_layout.addWidget(CardTitle("Conversations", sessions_card))
        self.session_list_widget = QListWidget(sessions_card)
        self.session_list_widget.setStyleSheet(
            f"background-color: {theme.BG_INSET}; border: 1px solid {theme.BORDER}; border-radius: 6px;"
        )
        self.session_list_widget.itemSelectionChanged.connect(self._on_session_selected)
        sessions_card_layout.addWidget(self.session_list_widget, 1)

        del_session_btn = DangerButton("Delete Session", sessions_card)
        del_session_btn.clicked.connect(self._delete_selected_session)
        sessions_card_layout.addWidget(del_session_btn)

        left_layout.addWidget(sessions_card, 1)

        # System Prompt & Parameters Card
        config_card = Card(left_panel)
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(12, 10, 12, 10)
        config_layout.setSpacing(8)

        config_layout.addWidget(CardTitle("System Prompt Template", config_card))

        self.template_combo = QComboBox(config_card)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        config_layout.addWidget(self.template_combo)

        self.system_prompt_edit = QPlainTextEdit(config_card)
        self.system_prompt_edit.setPlaceholderText("Enter system prompt...")
        self.system_prompt_edit.setMaximumHeight(80)
        self.system_prompt_edit.textChanged.connect(self._on_system_prompt_edited)
        config_layout.addWidget(self.system_prompt_edit)

        config_layout.addWidget(QLabel("Temperature:", config_card))
        self.temp_slider = SliderDoubleSpinBox(0.0, 2.0, 2, config_card)
        self.temp_slider.setSingleStep(0.05)
        self.temp_slider.setValue(0.7)
        self.temp_slider.valueChanged.connect(self._on_params_changed)
        config_layout.addWidget(self.temp_slider)


        config_layout.addWidget(QLabel("Max Tokens:", config_card))
        self.max_tokens_spin = QSpinBox(config_card)
        self.max_tokens_spin.setRange(64, 32768)
        self.max_tokens_spin.setValue(2048)
        self.max_tokens_spin.setSingleStep(256)
        self.max_tokens_spin.valueChanged.connect(self._on_params_changed)
        config_layout.addWidget(self.max_tokens_spin)

        left_layout.addWidget(config_card)

        # =====================================================================
        # RIGHT PANEL: Active Conversation & Input
        # =====================================================================
        right_panel = QWidget(main_splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # Top Bar: Status & Actions
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.endpoint_status_chip = Chip("Endpoint: Checking...", "muted", right_panel)
        top_bar.addWidget(self.endpoint_status_chip)

        top_bar.addStretch(1)

        clear_btn = SecondaryButton("Clear Chat", right_panel)
        clear_btn.clicked.connect(self._clear_current_chat)
        top_bar.addWidget(clear_btn)

        right_layout.addLayout(top_bar)

        # Chat Transcript Scroll Area
        self.chat_scroll = QScrollArea(right_panel)
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setStyleSheet(f"background-color: {theme.BG_INSET}; border-radius: 8px;")

        self.chat_container = QWidget()
        self.chat_container.setObjectName("ChatContainer")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(16, 14, 16, 14)
        self.chat_layout.setSpacing(12)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.chat_scroll.setWidget(self.chat_container)
        right_layout.addWidget(self.chat_scroll, 1)

        # Pending Image Attachments Bar
        self.image_bar = QWidget(right_panel)
        self.image_bar_layout = QHBoxLayout(self.image_bar)
        self.image_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.image_bar_layout.setSpacing(8)
        self.image_bar_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.image_bar.setVisible(False)
        right_layout.addWidget(self.image_bar)

        # Input Row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.attach_btn = SecondaryButton("📷 Attach Image", right_panel)
        self.attach_btn.setToolTip("Attach PNG/JPG/WEBP image for multimodal vision prompts")
        self.attach_btn.clicked.connect(self._attach_images)
        input_row.addWidget(self.attach_btn)

        self.chat_input = ChatInputEdit(right_panel)
        self.chat_input.send_requested.connect(self._send_message)
        input_row.addWidget(self.chat_input, 1)

        self.send_btn = QPushButton("Send 🚀", right_panel)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        self.stop_btn = DangerButton("Stop ⏹", right_panel)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._stop_generation)
        input_row.addWidget(self.stop_btn)

        right_layout.addLayout(input_row)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([300, 700])

        self._layout.addWidget(main_splitter)

        # Timer for polling local endpoint health
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(4000)
        self._health_timer.timeout.connect(self._check_endpoint_health)

        # Initial load
        self._load_templates()
        self._refresh_sessions_list()
        self._check_endpoint_health()
        self._health_timer.start()

    # -- Session Management ---------------------------------------------------

    def _refresh_sessions_list(self) -> None:
        self.session_list_widget.blockSignals(True)
        self.session_list_widget.clear()
        sessions = self.chat_store.load_sessions()

        for s in sessions:
            item = QListWidgetItem(f"💬 {s.title}")
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.session_list_widget.addItem(item)

        self.session_list_widget.blockSignals(False)

        if not sessions:
            self._create_new_session()
        else:
            self.session_list_widget.setCurrentRow(0)
            self._load_session(sessions[0].id)

    def _create_new_session(self) -> None:
        sys_prompt = "You are a helpful, respectful, and honest AI assistant."
        if self.template_combo.count() > 0:
            template = self.template_combo.currentData()
            if isinstance(template, SystemPromptTemplate):
                sys_prompt = template.prompt

        new_sess = ChatSession(
            id=uuid.uuid4().hex,
            title=f"Chat {len(self.chat_store.load_sessions()) + 1}",
            system_prompt=sys_prompt,
            temperature=self.temp_slider.value(),
            max_tokens=self.max_tokens_spin.value(),
        )
        self.chat_store.upsert_session(new_sess)
        self._refresh_sessions_list()

    def _on_session_selected(self) -> None:
        items = self.session_list_widget.selectedItems()
        if not items:
            return
        sess_id = items[0].data(Qt.ItemDataRole.UserRole)
        if sess_id:
            self._load_session(sess_id)

    def _load_session(self, session_id: str) -> None:
        session = self.chat_store.get_session(session_id)
        if not session:
            return

        self.current_session = session

        # Block signals while updating controls
        self.system_prompt_edit.blockSignals(True)
        self.temp_slider.blockSignals(True)
        self.max_tokens_spin.blockSignals(True)

        self.system_prompt_edit.setPlainText(session.system_prompt)
        self.temp_slider.setValue(session.temperature)
        self.max_tokens_spin.setValue(session.max_tokens)

        self.system_prompt_edit.blockSignals(False)
        self.temp_slider.blockSignals(False)
        self.max_tokens_spin.blockSignals(False)

        # Clear & populate message bubbles
        self._clear_transcript_ui()
        for msg in session.messages:
            self._add_message_bubble(msg)

    def _delete_selected_session(self) -> None:
        if not self.current_session:
            return
        sess_id = self.current_session.id
        self.chat_store.delete_session(sess_id)
        self.current_session = None
        self._refresh_sessions_list()

    def _clear_current_chat(self) -> None:
        if self.current_session:
            self.current_session.messages.clear()
            self.chat_store.upsert_session(self.current_session)
            self._clear_transcript_ui()

    def _clear_transcript_ui(self) -> None:
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _add_message_bubble(self, message: ChatMessage) -> MessageBubble:
        bubble = MessageBubble(message, self.chat_container)
        self.chat_layout.addWidget(bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)
        return bubble

    def _scroll_to_bottom(self) -> None:
        self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        )

    # -- Templates & Parameters -----------------------------------------------

    def _load_templates(self) -> None:
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        templates = self.chat_store.load_templates()

        for t in templates:
            self.template_combo.addItem(t.name, t)

        self.template_combo.blockSignals(False)

    def _on_template_changed(self) -> None:
        template = self.template_combo.currentData()
        if isinstance(template, SystemPromptTemplate):
            self.system_prompt_edit.setPlainText(template.prompt)
            if self.current_session:
                self.current_session.system_prompt = template.prompt
                self.chat_store.upsert_session(self.current_session)

    def _on_system_prompt_edited(self) -> None:
        if self.current_session:
            self.current_session.system_prompt = self.system_prompt_edit.toPlainText()
            self.chat_store.upsert_session(self.current_session)

    def _on_params_changed(self) -> None:
        if self.current_session:
            self.current_session.temperature = self.temp_slider.value()
            self.current_session.max_tokens = self.max_tokens_spin.value()
            self.chat_store.upsert_session(self.current_session)

    # -- Multimodal Image Attachments -----------------------------------------

    def _attach_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images for Vision Prompt",
            "",
            "Image Files (*.png *.jpg *.jpeg *.webp)",
        )
        if files:
            for f in files:
                if f not in self.pending_images:
                    self.pending_images.append(f)
            self._update_image_bar()

    def _remove_image(self, path: str) -> None:
        if path in self.pending_images:
            self.pending_images.remove(path)
        self._update_image_bar()

    def _update_image_bar(self) -> None:
        while self.image_bar_layout.count():
            item = self.image_bar_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.pending_images:
            self.image_bar.setVisible(False)
            return

        self.image_bar.setVisible(True)
        for img_path in self.pending_images:
            card = QFrame(self.image_bar)
            card.setStyleSheet(
                f"background-color: {theme.BG_RAISED}; border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 4px;"
            )
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(4, 2, 4, 2)
            card_layout.setSpacing(6)

            pix = QPixmap(img_path)
            if not pix.isNull():
                thumb = QLabel(card)
                thumb.setPixmap(pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                card_layout.addWidget(thumb)

            name_lbl = QLabel(Path(img_path).name[:16], card)
            name_lbl.setStyleSheet("font-size: 11px;")
            card_layout.addWidget(name_lbl)

            rm_btn = QPushButton("×", card)
            rm_btn.setFixedSize(18, 18)
            rm_btn.setStyleSheet(
                f"background: transparent; color: {theme.DANGER}; border: none; font-weight: bold;"
            )
            rm_btn.clicked.connect(lambda _=False, p=img_path: self._remove_image(p))
            card_layout.addWidget(rm_btn)

            self.image_bar_layout.addWidget(card)

    # -- Health Probe ---------------------------------------------------------

    def _check_endpoint_health(self) -> None:
        if getattr(self, "_health_worker", None) and self._health_worker.isRunning():
            return
        config = self.config_store.load()
        self._health_worker = _HealthCheckThread(config.host, config.port, self)
        self._health_worker.status_ready.connect(self._on_health_status_ready)
        self._health_worker.start()

    def _on_health_status_ready(self, status, host: str, port: int) -> None:
        self.endpoint_status_chip.setTextFormat(Qt.TextFormat.RichText)
        if status.reachable:
            self.endpoint_status_chip.setText(
                f'Endpoint: http://{host}:{port}/v1/chat/completions &nbsp;'
                f'<span style="color: #22c55e; font-weight: bold; background-color: #14532d; padding: 2px 8px; border-radius: 4px;">ONLINE</span>'
            )
            self.endpoint_status_chip.setProperty("chipStyle", "success")
        else:
            self.endpoint_status_chip.setText(
                f'Endpoint: http://{host}:{port} &nbsp;'
                f'<span style="color: #ef4444; font-weight: bold; background-color: #450a0a; padding: 2px 8px; border-radius: 4px;">OFFLINE</span>'
            )
            self.endpoint_status_chip.setProperty("chipStyle", "danger")

        self.endpoint_status_chip.style().unpolish(self.endpoint_status_chip)
        self.endpoint_status_chip.style().polish(self.endpoint_status_chip)




    # -- Message Sending & Streaming ------------------------------------------

    def _send_message(self) -> None:
        text = self.chat_input.toPlainText().strip()
        if not text and not self.pending_images:
            return

        if not self.current_session:
            self._create_new_session()

        # Update session title if it's the first message
        if not self.current_session.messages and text:
            self.current_session.title = text[:28] + ("..." if len(text) > 28 else "")

        # User Message
        user_msg = ChatMessage(
            id=uuid.uuid4().hex,
            role="user",
            content=text,
            image_paths=list(self.pending_images),
        )
        self.current_session.messages.append(user_msg)

        # Clear inputs & image bar
        self.chat_input.clear()
        self.pending_images.clear()
        self._update_image_bar()

        # Add user message bubble
        self._add_message_bubble(user_msg)

        # Create Assistant Message placeholder
        assistant_msg = ChatMessage(
            id=uuid.uuid4().hex,
            role="assistant",
            content="",
        )
        self.current_session.messages.append(assistant_msg)
        assistant_bubble = self._add_message_bubble(assistant_msg)

        # Save session
        self.chat_store.upsert_session(self.current_session)
        self._refresh_sessions_list_quiet()

        # UI state: disable send, show stop
        self.send_btn.setEnabled(False)
        self.attach_btn.setEnabled(False)
        self.stop_btn.setVisible(True)

        # Start streaming worker thread
        config = self.config_store.load()
        endpoint_url = f"http://{config.host}:{config.port}/v1/chat/completions"

        self.active_worker = ChatStreamWorker(
            endpoint_url=endpoint_url,
            messages=self.current_session.messages[:-1],  # send messages up to current user prompt
            system_prompt=self.current_session.system_prompt,
            temperature=self.current_session.temperature,
            max_tokens=self.current_session.max_tokens,
            stream=True,
        )

        self.active_worker.token_received.connect(assistant_bubble.append_text)
        self.active_worker.finished.connect(lambda full_txt: self._on_stream_finished(assistant_msg, full_txt))
        self.active_worker.error.connect(lambda err_msg: self._on_stream_error(assistant_bubble, assistant_msg, err_msg))
        self.active_worker.start()

    def _on_stream_finished(self, assistant_msg: ChatMessage, full_text: str) -> None:
        assistant_msg.content = full_text
        if self.current_session:
            self.chat_store.upsert_session(self.current_session)

        self.send_btn.setEnabled(True)
        self.attach_btn.setEnabled(True)
        self.stop_btn.setVisible(False)
        self.active_worker = None
        self._scroll_to_bottom()

    def _on_stream_error(self, assistant_bubble: MessageBubble, assistant_msg: ChatMessage, error_msg: str) -> None:
        if "10061" in error_msg or "connection refused" in error_msg.lower() or "deneg" in error_msg.lower():
            err_display = (
                "\n⚠️ [El servidor de IA está APAGADO]\n\n"
                "Para poder chatear con la IA:\n"
                "1. Ve a la pestaña 'Run' en el menú lateral izquierdo.\n"
                "2. Selecciona tu modelo y presiona el botón ▶️ Iniciar Servidor.\n"
                "3. Regresa a esta pestaña 'Chat' cuando el indicador marque (Online)."
            )
        else:
            err_display = f"\n[Error al conectar con el servidor: {error_msg}]"

        assistant_bubble.append_text(err_display)
        assistant_msg.content += err_display
        if self.current_session:
            self.chat_store.upsert_session(self.current_session)

        self.send_btn.setEnabled(True)
        self.attach_btn.setEnabled(True)
        self.stop_btn.setVisible(False)
        self.active_worker = None


    def _stop_generation(self) -> None:
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.cancel()
            self.active_worker.terminate()
            self.active_worker = None
        self.send_btn.setEnabled(True)
        self.attach_btn.setEnabled(True)
        self.stop_btn.setVisible(False)

    def _refresh_sessions_list_quiet(self) -> None:
        self.session_list_widget.blockSignals(True)
        self.session_list_widget.clear()
        sessions = self.chat_store.load_sessions()
        curr_id = self.current_session.id if self.current_session else None

        for s in sessions:
            item = QListWidgetItem(f"💬 {s.title}")
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.session_list_widget.addItem(item)
            if s.id == curr_id:
                item.setSelected(True)

        self.session_list_widget.blockSignals(False)

    def deferred_refresh(self) -> None:
        """Asynchronous, non-blocking health probe on tab navigation."""
        self._check_endpoint_health()

    def _refresh(self) -> None:
        self._check_endpoint_health()


__all__ = ["ChatPage"]

