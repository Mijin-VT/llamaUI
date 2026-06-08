"""Phase 8 smoke: runtime process control and argv building.

Uses ``/bin/sh`` (or Python) as a stand-in binary — no real llama-server
required.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QT_ROOT = REPO_ROOT / "qt_app"
for candidate in (REPO_ROOT, QT_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from llama_data import (  # noqa: E402
    AppConfig,
    LLAMA_OPTION_CATALOG,
    LocalModel,
    ModelProfile,
    SettingValueMap,
    default_paths,
)
from llama_data.llama_options import LlamaOptionValue, OptionKind  # noqa: E402
from app.services.runtime import (  # noqa: E402
    LogBuffer,
    LogLine,
    LlamaServerController,
    RuntimeStatus,
    ServerState,
    build_argv,
    is_port_available,
)
from app.services.runtime_api import (  # noqa: E402
    ApiStatus,
    LlamaServerApiClient,
    SwitchResult,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  pass {message}")


# ---- argv building -------------------------------------------------------


def test_build_argv_minimal() -> None:
    print("[argv] minimal config + model")
    with tempfile.TemporaryDirectory() as td:
        model_file = Path(td) / "test.gguf"
        model_file.write_bytes(b"\x00" * 16)

        config = AppConfig(llama_server_path="/usr/bin/llama-server")
        model = LocalModel.from_path(str(model_file))

        argv = build_argv(config, model)
        check(argv[0] == "/usr/bin/llama-server", "binary path is first")
        check("--model" in argv, "--model flag present")
        check(str(model_file) in argv, "model path present")
        check("--host" in argv, "--host flag present")
        check("--port" in argv, "--port flag present")
        check("8080" in argv, "default port 8080")


def test_build_argv_with_profile() -> None:
    print("[argv] config + model + profile")
    with tempfile.TemporaryDirectory() as td:
        model_file = Path(td) / "model.gguf"
        model_file.write_bytes(b"\x00" * 16)

        config = AppConfig(llama_server_path="/usr/bin/llama-server", port=9999)
        model = LocalModel.from_path(str(model_file))

        settings = SettingValueMap({
            "ctx_size": LlamaOptionValue(OptionKind.INTEGER, 4096),
            "n_gpu_layers": LlamaOptionValue(OptionKind.INTEGER, 99),
            "temp": LlamaOptionValue(OptionKind.FLOAT, 0.7),
            "verbose": LlamaOptionValue(OptionKind.BOOLEAN, True),
        })
        profile = ModelProfile(
            id="p1", model_id=model.id, name="test-profile",
            settings=settings,
            raw_args=["--special-arg", "val"],
        )

        argv = build_argv(config, model, profile)

        check("--port" in argv and "9999" in argv, "config port overrides profile")
        check("--ctx-size" in argv and "4096" in argv, "profile ctx_size rendered")
        check("--n-gpu-layers" in argv and "99" in argv, "profile n_gpu_layers rendered")
        check("--temp" in argv and "0.7" in argv, "profile temp rendered")
        check("--verbose" in argv, "profile boolean True emitted as flag")
        check("--special-arg" in argv and "val" in argv, "raw_args appended")

        # model/host/port from profile should NOT duplicate.
        model_count = argv.count("--model")
        check(model_count == 1, f"--model appears exactly once (got {model_count})")


def test_build_argv_no_binary_raises() -> None:
    print("[argv] missing binary raises ValueError")
    config = AppConfig(llama_server_path=None)
    model = LocalModel(id="x", path="/fake.gguf")
    try:
        build_argv(config, model)
        check(False, "should have raised")
    except ValueError:
        check(True, "ValueError raised for missing binary path")


# ---- LogBuffer -----------------------------------------------------------


def test_log_buffer() -> None:
    print("[logbuffer] append / search / clear")
    buf = LogBuffer(maxlen=100)
    check(len(buf) == 0, "starts empty")

    buf.append(LogLine(source="stdout", text="hello world"))
    buf.append(LogLine(source="stderr", text="error occurred"))
    buf.append(LogLine(source="stdout", text="another line"))
    check(len(buf) == 3, "three entries")

    results = buf.search("error")
    check(len(results) == 1, "search finds 'error'")
    check(results[0].source == "stderr", "search result has correct source")

    results = buf.search("hello", source="stdout")
    check(len(results) == 1, "filtered search finds 'hello' in stdout")

    buf.clear()
    check(len(buf) == 0, "clear empties buffer")


# ---- Port check ----------------------------------------------------------


def test_port_available() -> None:
    print("[port] availability check")
    # Pick a very-high port that is extremely unlikely to be in use.
    check(is_port_available("127.0.0.1", 59999), "high port is available")


# ---- Process lifecycle with /bin/sh stand-in -----------------------------


def _find_test_binary() -> str:
    """Return a small executable we can use as a llama-server stand-in."""
    for candidate in ("/bin/sh", "/usr/bin/sh", "/bin/bash", "/usr/bin/bash"):
        if Path(candidate).is_file():
            return candidate
    return sys.executable  # python as last resort


def test_process_lifecycle() -> None:
    print("[process] start / stop / status lifecycle")
    binary = _find_test_binary()
    ctrl = LlamaServerController()

    # Use sh to echo something then sleep — simulates a server that prints to
    # stdout and stays alive.
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "serve.sh"
        script.write_text("#!/bin/sh\necho 'server started'\necho 'err msg' >&2\nsleep 30\n")
        os.chmod(script, 0o755)

        argv = [binary, str(script)]
        status = ctrl.start(argv, host="127.0.0.1", port=59998,
                            model_path="/fake/model.gguf", profile_name="smoke")

        check(status.state == ServerState.RUNNING, f"state is RUNNING (got {status.state.value})")
        check(status.pid is not None, "pid assigned")
        check(status.model_path == "/fake/model.gguf", "model_path tracked")
        check(status.profile_name == "smoke", "profile_name tracked")
        check(status.host == "127.0.0.1", "host tracked")
        check(status.port == 59998, "port tracked")
        check(len(status.command) == 2, "command recorded")

        # Give the readers time to capture output.
        time.sleep(0.5)

        logs = ctrl.log_buffer.lines()
        check(len(logs) >= 1, f"log buffer has entries (got {len(logs)})")
        stdout_lines = [ln for ln in logs if ln.source == "stdout"]
        stderr_lines = [ln for ln in logs if ln.source == "stderr"]
        check(len(stdout_lines) >= 1, f"stdout captured (got {len(stdout_lines)})")
        check(len(stderr_lines) >= 1, f"stderr captured (got {len(stderr_lines)})")
        check("server started" in stdout_lines[0].text, "stdout content matches")
        check("err msg" in stderr_lines[0].text, "stderr content matches")

        # Each log line has a timestamp.
        for ln in logs:
            check(len(ln.timestamp) > 10, f"timestamp present: {ln.timestamp[:10]}")

        # Stop.
        status = ctrl.stop(timeout=3.0)
        check(status.state == ServerState.STOPPED, f"state is STOPPED (got {status.state.value})")
        check(status.exit_code is not None, "exit code set after stop")

        # After stop, buffer is NOT cleared automatically (caller decides).
        check(len(ctrl.log_buffer) > 0, "log buffer preserved after stop")


def test_restart() -> None:
    print("[process] restart cycle")
    binary = _find_test_binary()
    ctrl = LlamaServerController()

    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "serve.sh"
        script.write_text("#!/bin/sh\necho 'first'\nsleep 30\n")
        os.chmod(script, 0o755)

        argv = [binary, str(script)]
        s1 = ctrl.start(argv, host="127.0.0.1", port=59997)
        check(s1.state == ServerState.RUNNING, "first start running")
        pid1 = s1.pid
        check(pid1 is not None, "first pid set")

        script2 = Path(td) / "serve2.sh"
        script2.write_text("#!/bin/sh\necho 'second'\nsleep 30\n")
        os.chmod(script2, 0o755)

        argv2 = [binary, str(script2)]
        s2 = ctrl.restart(argv2, host="127.0.0.1", port=59997,
                          model_path="/other.gguf", profile_name="restart-test")
        check(s2.state == ServerState.RUNNING, "restart running")
        check(s2.pid != pid1, "restart gets new pid")
        check(s2.model_path == "/other.gguf", "restart model_path updated")

        ctrl.stop(timeout=3.0)


def test_start_port_conflict() -> None:
    print("[process] port conflict detection")
    binary = _find_test_binary()
    ctrl = LlamaServerController()

    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "serve.sh"
        script.write_text("#!/bin/sh\nsleep 30\n")
        os.chmod(script, 0o755)
        argv = [binary, str(script)]
        s1 = ctrl.start(argv, host="127.0.0.1", port=59996)
        check(s1.state == ServerState.RUNNING, "first instance running")

        # Second controller tries same port.
        ctrl2 = LlamaServerController()
        try:
            ctrl2.start([binary, str(script)], host="127.0.0.1", port=59996)
            check(False, "should have raised for port conflict")
        except RuntimeError as exc:
            check("already in use" in str(exc), f"port conflict message: {exc}")

        ctrl.stop(timeout=3.0)


def test_start_already_running() -> None:
    print("[process] double-start rejected")
    binary = _find_test_binary()
    ctrl = LlamaServerController()

    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "serve.sh"
        script.write_text("#!/bin/sh\nsleep 30\n")
        os.chmod(script, 0o755)
        argv = [binary, str(script)]
        ctrl.start(argv, host="127.0.0.1", port=59995)

        try:
            ctrl.start(argv, host="127.0.0.1", port=59995)
            check(False, "should have raised for double start")
        except RuntimeError as exc:
            check("already running" in str(exc), f"already-running message: {exc}")

        ctrl.stop(timeout=3.0)


def test_start_missing_binary() -> None:
    print("[process] missing binary rejected")
    ctrl = LlamaServerController()
    try:
        ctrl.start(["/nonexistent/binary"], host="127.0.0.1", port=59994)
        check(False, "should have raised FileNotFoundError")
    except FileNotFoundError:
        check(True, "FileNotFoundError for missing binary")


# ---- API client (no real server) ----------------------------------------


def test_api_client_unreachable() -> None:
    print("[api] unreachable server returns ApiStatus")
    client = LlamaServerApiClient(host="127.0.0.1", port=59993, timeout=0.5)
    status = client.status()
    check(isinstance(status, ApiStatus), "ApiStatus returned")
    check(not status.reachable, "unreachable server")
    check(status.error is not None, "error message present")


def test_switch_model_unreachable() -> None:
    print("[api] switch_model on unreachable returns restart_required")
    client = LlamaServerApiClient(host="127.0.0.1", port=59993, timeout=0.5)
    result = client.switch_model("/fake/model.gguf")
    check(isinstance(result, SwitchResult), "SwitchResult returned")
    check(result.restart_required, "restart required when unreachable")


def test_poll_health_no_server() -> None:
    print("[controller] poll_health with no running server")
    ctrl = LlamaServerController()
    api = ctrl.poll_health()
    check(isinstance(api, ApiStatus), "ApiStatus returned")
    check(not api.reachable, "not reachable when no server")


# ---- Status snapshot immutability ----------------------------------------


def test_status_is_copy() -> None:
    print("[status] status returns independent copies")
    ctrl = LlamaServerController()
    s1 = ctrl.status
    s2 = ctrl.status
    check(s1 is not s2, "different objects")
    check(s1.state == s2.state, "same state value")


# ---- Imports smoke -------------------------------------------------------


def test_package_exports() -> None:
    print("[imports] runtime types importable from services package")
    from app.services import (
        ApiStatus,
        LlamaServerApiClient,
        LlamaServerController,
        LogLine,
        RuntimeStatus,
        ServerState,
        SwitchResult,
        build_argv,
        is_port_available,
    )
    check(ServerState.HEALTHY is not None, "ServerState.HEALTHY exists")
    check(ServerState.UNHEALTHY is not None, "ServerState.UNHEALTHY exists")
    check(callable(build_argv), "build_argv callable")
    check(callable(is_port_available), "is_port_available callable")


# ---- Main ----------------------------------------------------------------


def main() -> int:
    print("=== Phase 8: Runtime smoke tests ===\n")
    test_build_argv_minimal()
    test_build_argv_with_profile()
    test_build_argv_no_binary_raises()
    test_log_buffer()
    test_port_available()
    test_process_lifecycle()
    test_restart()
    test_start_port_conflict()
    test_start_already_running()
    test_start_missing_binary()
    test_api_client_unreachable()
    test_switch_model_unreachable()
    test_poll_health_no_server()
    test_status_is_copy()
    test_package_exports()
    print("\n=== All Phase 8 smoke tests passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
