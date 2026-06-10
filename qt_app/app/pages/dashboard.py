from __future__ import annotations

import re
import time
from collections import deque
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..services.runtime import LlamaServerController, LogLine, ServerState
from ..services.runtime_api import ApiStatus, LlamaServerApiClient
from ..widgets.buttons import SecondaryButton
from ..widgets.cards import Card, CardTitle, Chip, FieldTile
from .base import PageBase, PagePolicy


class _RollingChart(QWidget):
    """Small dependency-free rolling line/area chart."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        color: str = theme.ACCENT,
        fill_color: str | None = None,
        suffix: str = "",
        dynamic_slot_color: bool = False,
    ) -> None:
        super().__init__(parent)
        self._values: deque[float] = deque(maxlen=120)
        self._color = color
        self._fill_color = fill_color or self._with_alpha(color, 48)
        self._suffix = suffix
        self._dynamic_slot_color = dynamic_slot_color
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAutoFillBackground(False)

    def add_value(self, value: float) -> None:
        self._values.append(max(0.0, float(value)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.fillRect(rect, QColor(theme.BG_INSET))

        plot = rect.adjusted(42, 18, -12, -30)
        painter.setPen(QPen(QColor(theme.BORDER_SOFT), 1))
        for i in range(5):
            y = plot.top() + (plot.height() * i / 4)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        for i in range(4):
            x = plot.left() + (plot.width() * i / 3)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        values = list(self._values)
        current = values[-1] if values else 0.0
        ymax = max(values) if values else 1.0
        ymax = max(1.0, ymax * 1.1)
        color = self._line_color(current)

        if values:
            points: list[QPointF] = []
            denom = max(1, len(values) - 1)
            for idx, value in enumerate(values):
                x = plot.left() + (plot.width() * idx / denom)
                y = plot.bottom() - (plot.height() * min(value, ymax) / ymax)
                points.append(QPointF(x, y))

            area = QPainterPath()
            area.moveTo(points[0].x(), plot.bottom())
            for point in points:
                area.lineTo(point)
            area.lineTo(points[-1].x(), plot.bottom())
            area.closeSubpath()
            painter.fillPath(area, self._fill_brush(color))

            line = QPainterPath(points[0])
            for point in points[1:]:
                line.lineTo(point)
            painter.setPen(QPen(QColor(color), 2))
            painter.drawPath(line)

        font = QFont(theme.FONT_MONO.family, theme.FONT_MONO.base_px)
        painter.setFont(font)
        painter.setPen(QColor(theme.FG_MUTED))
        painter.drawText(QRectF(4, plot.top() - 2, 36, 16), Qt.AlignmentFlag.AlignRight, self._format_value(ymax))
        painter.drawText(QRectF(4, plot.bottom() - 12, 36, 16), Qt.AlignmentFlag.AlignRight, "0")
        painter.drawText(QRectF(plot.left(), plot.bottom() + 8, 80, 16), Qt.AlignmentFlag.AlignLeft, "-2m")
        painter.drawText(QRectF(plot.right() - 80, plot.bottom() + 8, 80, 16), Qt.AlignmentFlag.AlignRight, "now")

        value_font = QFont(theme.FONT_MONO.family, theme.FONT_MONO.base_px + 3)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QColor(color))
        painter.drawText(rect.adjusted(0, 8, -14, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, self._format_value(current))

    def _line_color(self, current: float) -> str:
        if self._dynamic_slot_color:
            return theme.DANGER if current >= 80.0 else theme.SUCCESS
        return self._color

    def _fill_brush(self, color: str) -> QColor:
        if self._dynamic_slot_color:
            return QColor(self._with_alpha(color, 48))
        return QColor(self._fill_color)

    def _format_value(self, value: float) -> str:
        if self._suffix == "%":
            return f"{value:.0f}%"
        if value >= 100:
            return f"{value:.0f}{self._suffix}"
        if value >= 10:
            return f"{value:.1f}{self._suffix}"
        return f"{value:.2f}{self._suffix}"

    @staticmethod
    def _with_alpha(color: str, alpha: int) -> str:
        qcolor = QColor(color)
        qcolor.setAlpha(alpha)
        return qcolor.name(QColor.NameFormat.HexArgb)


class DashboardPage(PageBase):
    policy = PagePolicy.FULL_WIDTH

    def __init__(self, parent=None):
        self._controller: Optional[LlamaServerController] = None
        self._metrics: deque[dict] = deque(maxlen=120)
        super().__init__(parent)

    def set_controller(self, controller: LlamaServerController) -> None:
        self._controller = controller
        self._refresh()

    def build(self) -> None:
        self.setProperty("subtitle", "Real-time server metrics, throughput charts, and streaming logs.")
        self._build_status_card()
        self._build_metrics_row()
        self._build_log_viewer()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _build_status_card(self) -> None:
        card = Card(self._body)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(CardTitle("Server status", card))
        header.addStretch(1)
        self._state_chip = Chip("Stopped", "muted", card)
        header.addWidget(self._state_chip)
        layout.addLayout(header)

        fields = QHBoxLayout()
        fields.setSpacing(10)
        self._model_tile = FieldTile("Model", "—", card)
        self._host_tile = FieldTile("Host", "—", card)
        self._pid_tile = FieldTile("PID", "—", card)
        self._uptime_tile = FieldTile("Uptime", "—", card)
        self._slots_tile = FieldTile("Slots", "—", card)
        for tile in (self._model_tile, self._host_tile, self._pid_tile, self._uptime_tile, self._slots_tile):
            fields.addWidget(tile)
        layout.addLayout(fields)
        self._layout.addWidget(card)

    def _build_metrics_row(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(14)
        self._throughput_chart = _RollingChart(self._body, color=theme.ACCENT, fill_color=theme.ACCENT_DIM, suffix=" tok/s")
        self._latency_chart = _RollingChart(self._body, color=theme.WARNING, suffix=" ms")
        self._slot_chart = _RollingChart(self._body, color=theme.SUCCESS, suffix="%", dynamic_slot_color=True)
        row.addWidget(self._chart_card("Throughput", self._throughput_chart), 1)
        row.addWidget(self._chart_card("Health latency", self._latency_chart), 1)
        row.addWidget(self._chart_card("Slot utilization", self._slot_chart), 1)
        self._layout.addLayout(row)

    def _chart_card(self, title: str, chart: _RollingChart) -> Card:
        card = Card(self._body)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(CardTitle(title, card))
        layout.addWidget(chart)
        return card

    def _build_log_viewer(self) -> None:
        logs = Card(self._body)
        logs.setObjectName("PageCard")
        logs_layout = QVBoxLayout(logs)
        logs_layout.setContentsMargins(16, 14, 16, 14)
        logs_layout.setSpacing(8)
        logs_layout.addWidget(CardTitle("Streaming logs", logs))

        filter_row = QHBoxLayout()
        self.log_search = QLineEdit(logs)
        self.log_search.setPlaceholderText("Search logs…")
        self.log_search.textChanged.connect(self._render_logs)
        self.log_source = QComboBox(logs)
        self.log_source.addItems(["all", "stdout", "stderr"])
        self.log_source.currentIndexChanged.connect(self._render_logs)
        copy_btn = SecondaryButton("Copy", logs)
        copy_btn.clicked.connect(self._copy_logs)
        clear_btn = SecondaryButton("Clear", logs)
        clear_btn.clicked.connect(self._clear_logs)
        filter_row.addWidget(self.log_search, 1)
        filter_row.addWidget(self.log_source)
        filter_row.addWidget(copy_btn)
        filter_row.addWidget(clear_btn)
        logs_layout.addLayout(filter_row)

        self.logs = QPlainTextEdit(logs)
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(10000)
        self.logs.setMinimumHeight(320)
        self.logs.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.logs.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {theme.BG_INSET}; border: 1px solid {theme.BORDER}; "
            f"border-radius: 6px; color: {theme.FG_PRIMARY}; {theme.font_css(theme.FONT_MONO)} }}"
        )
        logs_layout.addWidget(self.logs)

        footer = QHBoxLayout()
        self.autoscroll = QCheckBox("Auto-scroll", logs)
        self.autoscroll.setChecked(True)
        self.line_count = QLabel("Showing 0 of 0 lines", logs)
        self.line_count.setObjectName("Muted")
        footer.addWidget(self.autoscroll)
        footer.addStretch(1)
        footer.addWidget(self.line_count)
        logs_layout.addLayout(footer)
        self._layout.addWidget(logs)

    def _poll(self) -> None:
        if not self._controller:
            return

        started = time.perf_counter()
        status = self._controller.status
        api = status.api_status
        props: ApiStatus | None = None
        client: LlamaServerApiClient | None = self._controller._api_client
        if api and api.reachable and client:
            props = client.fetch_props()
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        self._update_status(status, props)

        metric = {
            "timestamp": time.time(),
            "reachable": bool(api and api.reachable),
            "health": api.health if api else None,
            "latency_ms": elapsed_ms if api and api.reachable else 0.0,
            "tokens_per_second": self._extract_tokens_per_second(api),
            "slot_utilization": self._slot_utilization(api, props),
        }
        self._metrics.append(metric)
        self._throughput_chart.add_value(metric["tokens_per_second"])
        self._latency_chart.add_value(metric["latency_ms"])
        self._slot_chart.add_value(metric["slot_utilization"])

        self._render_logs()

    def _refresh(self) -> None:
        if not self._controller:
            return
        self._poll()

    def _update_status(self, status, props: ApiStatus | None = None) -> None:
        self._set_state_chip(status.state)
        api = props if props and props.reachable else status.api_status
        model = (api.model_path if api and api.model_path else status.model_path) or "—"
        if model != "—":
            model = Path(model).name
        self._model_tile.set_value(model)
        self._host_tile.set_value(f"{status.host}:{status.port}")
        self._pid_tile.set_value(str(status.pid) if status.pid is not None else "—")
        self._uptime_tile.set_value(self._format_uptime())
        total_slots = api.total_slots if api and api.total_slots is not None else None
        self._slots_tile.set_value(f"0 / {total_slots}" if total_slots else "—")

    def _set_state_chip(self, state: ServerState) -> None:
        text = state.value.title()
        self._state_chip.setText(text)
        self._state_chip.setStyleSheet("")
        if state == ServerState.HEALTHY:
            self._state_chip.set_style("success")
        elif state in {ServerState.ERROR, ServerState.UNHEALTHY, ServerState.EXITED}:
            self._state_chip.set_style("muted")
            self._state_chip.setStyleSheet(
                f"background-color: {theme.DANGER}; color: {theme.FG_PRIMARY}; border-radius: 9px; padding: 2px 8px;"
            )
        elif state in {ServerState.STARTING, ServerState.RUNNING, ServerState.STOPPING}:
            self._state_chip.set_style("warning")
        else:
            self._state_chip.set_style("muted")

    def _render_logs(self) -> None:
        if not self._controller:
            self.logs.clear()
            self.line_count.setText("Showing 0 of 0 lines")
            return
        query = self.log_search.text().strip().lower()
        source = self.log_source.currentText()
        lines: list[LogLine] = self._controller.log_buffer.lines()
        rendered: list[str] = []
        for line in lines:
            if source != "all" and line.source != source:
                continue
            if query and query not in line.text.lower():
                continue
            rendered.append(f"{line.timestamp} [{line.source}] {line.text}")
        visible = rendered[-10000:]
        self.logs.setPlainText("\n".join(visible))
        if self.autoscroll.isChecked():
            cursor = self.logs.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.logs.setTextCursor(cursor)
        self.line_count.setText(f"Showing {len(visible)} of {len(lines)} lines")

    def _copy_logs(self) -> None:
        text = self.logs.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _clear_logs(self) -> None:
        if self._controller:
            self._controller.log_buffer.clear()
        self.logs.clear()
        self.line_count.setText("Showing 0 of 0 lines")

    def _format_uptime(self) -> str:
        if not self._metrics:
            return "—"
        seconds = max(0, int(time.time() - float(self._metrics[0]["timestamp"])))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {sec:02d}s"
        if minutes:
            return f"{minutes}m {sec:02d}s"
        return f"{sec}s"

    def _slot_utilization(self, api: ApiStatus | None, props: ApiStatus | None) -> float:
        total = None
        for status in (props, api):
            if status and status.total_slots:
                total = status.total_slots
                break
        if not total:
            return 0.0
        active = 0
        return min(100.0, max(0.0, (active / total) * 100.0))

    @staticmethod
    def _extract_tokens_per_second(api: ApiStatus | None) -> float:
        if not api or not api.health:
            return 0.0
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:tok/s|tokens?/s|t/s)", api.health, re.IGNORECASE)
        return float(match.group(1)) if match else 0.0


__all__ = ["DashboardPage"]
