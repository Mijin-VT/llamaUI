"""Local llama-server process lifecycle controller.

Builds argv from ``AppConfig`` + ``ModelProfile``, manages start/stop/restart,
captures stdout/stderr with timestamps, tracks health via the API client, and
detects port conflicts before launch.

This module is UI-independent. Qt signals / UI wiring live in the app layer.
"""
from __future__ import annotations

import socket
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Deque, List, Optional, Sequence

from llama_data import AppConfig, LLAMA_OPTION_CATALOG, LocalModel, ModelProfile

from .runtime_api import ApiStatus, LlamaServerApiClient


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class ServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    EXITED = "exited"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Log capture
# ---------------------------------------------------------------------------


@dataclass
class LogLine:
    source: str          # "stdout" | "stderr"
    text: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LogBuffer:
    """Thread-safe ring buffer that accumulates :class:`LogLine` entries.

    Provides ``search`` (case-insensitive substring match) and ``clear``.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._lines: Deque[LogLine] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, line: LogLine) -> None:
        with self._lock:
            self._lines.append(line)

    def lines(self) -> List[LogLine]:
        with self._lock:
            return list(self._lines)

    def search(self, query: str, source: Optional[str] = None) -> List[LogLine]:
        q = query.lower()
        with self._lock:
            return [
                ln
                for ln in self._lines
                if q in ln.text.lower()
                and (source is None or ln.source == source)
            ]

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._lines)


LogCallback = Callable[[LogLine], None]


# ---------------------------------------------------------------------------
# Status snapshot
# ---------------------------------------------------------------------------


@dataclass
class RuntimeStatus:
    state: ServerState
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    last_error: Optional[str] = None
    command: list[str] = field(default_factory=list)
    host: str = "127.0.0.1"
    port: int = 8080
    model_path: Optional[str] = None
    profile_name: Optional[str] = None
    api_status: Optional[ApiStatus] = None

    @property
    def is_running(self) -> bool:
        return self.state in {ServerState.RUNNING, ServerState.HEALTHY, ServerState.UNHEALTHY}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_port_available(host: str, port: int) -> bool:
    """Return *True* when nothing is listening on *host*:*port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def build_argv(
    config: AppConfig,
    model: LocalModel,
    profile: Optional[ModelProfile] = None,
) -> list[str]:
    """Build the full argv for llama-server from config, model, and profile.

    Model path, host, and port from *config* always take precedence over
    profile settings to avoid confusing mismatches.
    """
    if not config.llama_server_path:
        raise ValueError("llama-server path is not configured")

    host = config.host
    port = config.port
    if profile is not None:
        host_value = profile.settings.get("host")
        port_value = profile.settings.get("port")
        if host_value and host_value.value:
            host = str(host_value.value)
        if port_value and port_value.value is not None:
            port = int(port_value.value)
    argv = [
        config.llama_server_path,
        "--model", model.path,
        "--host", host,
        "--port", str(port),
    ]

    # Global defaults first.
    argv.extend(config.global_settings.to_argv(LLAMA_OPTION_CATALOG))

    # Profile settings overlay (skip model/host/port to avoid duplicates).
    if profile is not None:
        skip_ids = {"model", "host", "port"}
        for option_id, value in profile.settings.items():
            if option_id in skip_ids:
                continue
            option = LLAMA_OPTION_CATALOG.get(option_id)
            if option is not None:
                argv.extend(value.to_argv(option))
        argv.extend(profile.raw_args)

    return argv


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

# Health-poll defaults.
_HEALTH_INTERVAL = 2.0       # seconds between polls
_HEALTH_TIMEOUT  = 2.0       # per-request timeout


class LlamaServerController:
    """Owns a local llama-server subprocess.

    Callers provide an optional ``on_log`` callback for real-time log
    streaming and/or use the built-in :attr:`log_buffer` for batch access.
    """

    def __init__(self, on_log: Optional[LogCallback] = None) -> None:
        self.on_log = on_log
        self.log_buffer = LogBuffer()
        self._process: Optional[subprocess.Popen[str]] = None
        self._status = RuntimeStatus(state=ServerState.STOPPED)
        self._lock = threading.Lock()
        self._api_client: Optional[LlamaServerApiClient] = None
        self._health_thread: Optional[threading.Thread] = None
        self._stop_health = threading.Event()


    def _status_copy_unlocked(self) -> RuntimeStatus:
        return RuntimeStatus(**self._status.__dict__)
    # -- public interface ---------------------------------------------------

    @property
    def status(self) -> RuntimeStatus:
        """Snapshot of the current process state (thread-safe copy)."""
        with self._lock:
            self._sync_state()
            return RuntimeStatus(**self._status.__dict__)

    def start(
        self,
        argv: list[str],
        host: str = "127.0.0.1",
        port: int = 8080,
        model_path: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> RuntimeStatus:
        """Launch llama-server with *argv*.

        Raises on pre-condition failure (already running, binary missing,
        port occupied).
        """
        with self._lock:
            if self._process and self._process.poll() is None:
                raise RuntimeError("llama-server is already running")
            if not Path(argv[0]).is_file():
                raise FileNotFoundError(argv[0])
            if not is_port_available(host, port):
                raise RuntimeError(f"port {host}:{port} is already in use")

            self.log_buffer.clear()
            self._status = RuntimeStatus(
                state=ServerState.STARTING,
                command=list(argv),
                host=host,
                port=port,
                model_path=model_path,
                profile_name=profile_name,
            )
            try:
                self._process = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except Exception as exc:
                self._status.state = ServerState.ERROR
                self._status.last_error = str(exc)
                raise

            self._status.state = ServerState.RUNNING
            self._status.pid = self._process.pid
            self._start_reader("stdout", self._process.stdout)
            self._start_reader("stderr", self._process.stderr)
            self._start_health_poll(host, port)
            return self._status_copy_unlocked()

    def stop(self, timeout: float = 5.0) -> RuntimeStatus:
        """Gracefully stop the running process (SIGTERM → SIGKILL)."""
        self._stop_health.set()
        with self._lock:
            proc = self._process
            if not proc or proc.poll() is not None:
                self._status.state = ServerState.STOPPED
                self._api_client = None
                return self._status_copy_unlocked()
            self._status.state = ServerState.STOPPING
            proc.terminate()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)

        with self._lock:
            self._status.state = ServerState.STOPPED
            self._status.exit_code = proc.returncode
            self._status.pid = None
            self._process = None
            self._api_client = None
            return self._status_copy_unlocked()

    def restart(
        self,
        argv: list[str],
        host: str = "127.0.0.1",
        port: int = 8080,
        model_path: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> RuntimeStatus:
        """Stop the current server and start a fresh one."""
        self.stop()
        return self.start(argv, host, port, model_path, profile_name)

    def poll_health(self) -> ApiStatus:
        """One-shot health check against the running server's API."""
        with self._lock:
            client = self._api_client
        if client is None:
            return ApiStatus(reachable=False, error="no running server")
        status = client.status()
        with self._lock:
            self._status.api_status = status
            if self._status.state in {ServerState.RUNNING, ServerState.HEALTHY, ServerState.UNHEALTHY}:
                self._status.state = (
                    ServerState.HEALTHY if status.reachable else ServerState.UNHEALTHY
                )
        return status

    def switch_model(self, model_path: str) -> "SwitchResult":
        """Try to switch the running model via the API.

        Returns a :class:`SwitchResult` indicating whether the API path was
        used or a clean restart is required.
        """
        from .runtime_api import SwitchResult

        with self._lock:
            client = self._api_client
        if client is None:
            return SwitchResult(
                used_api=False,
                restart_required=True,
                message="no running server; start first",
            )
        return client.switch_model(model_path)

    def note_model_switched(self, model_path: str, profile_name: Optional[str] = None) -> None:
        with self._lock:
            self._status.model_path = model_path
            if profile_name is not None:
                self._status.profile_name = profile_name

    # -- internal -----------------------------------------------------------

    def _sync_state(self) -> None:
        """Reflect process exit into status (caller holds lock)."""
        if (
            self._process
            and self._process.poll() is not None
            and self._status.state
            in {ServerState.RUNNING, ServerState.STARTING, ServerState.HEALTHY, ServerState.UNHEALTHY}
        ):
            self._status.state = ServerState.EXITED
            self._status.exit_code = self._process.returncode
            self._status.pid = None

    def _emit(self, line: LogLine) -> None:
        self.log_buffer.append(line)
        if self.on_log:
            self.on_log(line)

    def _start_reader(self, source: str, pipe) -> None:
        if pipe is None:
            return

        def run() -> None:
            for raw in pipe:
                self._emit(LogLine(source=source, text=raw.rstrip()))

        t = threading.Thread(target=run, name=f"llama-server-{source}", daemon=True)
        t.start()

    def _start_health_poll(self, host: str, port: int) -> None:
        self._stop_health.set()
        self._stop_health.clear()
        self._api_client = LlamaServerApiClient(
            host=host, port=port, timeout=_HEALTH_TIMEOUT
        )

        def loop() -> None:
            while not self._stop_health.wait(_HEALTH_INTERVAL):
                if self._process and self._process.poll() is not None:
                    return
                self.poll_health()

        t = threading.Thread(target=loop, name="llama-server-health", daemon=True)
        t.start()
        self._health_thread = t


__all__ = [
    "ServerState",
    "LogLine",
    "LogBuffer",
    "RuntimeStatus",
    "LogCallback",
    "LlamaServerController",
    "build_argv",
    "is_port_available",
]
