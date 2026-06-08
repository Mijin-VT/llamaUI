from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QT_ROOT = REPO_ROOT / "qt_app"
for candidate in (REPO_ROOT, QT_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.services import (  # noqa: E402
    FrameworkDiagnostics,
    GpuVendor,
    LlamaServerProbe,
    available_qt_platform_plugins,
    framework_diagnostics,
    validate_llama_server,
)
from llama_data import AppConfig, ConfigStore, LibraryStore, LocalModel, ModelProfile, ProfileStore, default_paths  # noqa: E402
from app.services.library_scan import ScanResult, infer_quant, scan_library  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"pass {message}")


def main() -> int:
    diag = framework_diagnostics()
    check(isinstance(diag, FrameworkDiagnostics), "framework diagnostics type")
    check(isinstance(diag.gpu_vendor, GpuVendor), "gpu vendor enum")
    check("wayland" in available_qt_platform_plugins(), "Qt Wayland plugin discoverable")
    json.dumps(diag.to_dict())

    missing = validate_llama_server("/nonexistent/llama-server")
    check(isinstance(missing, LlamaServerProbe), "llama probe type")
    check(not missing.exists, "missing binary rejected")

    with tempfile.TemporaryDirectory() as td:
        paths = default_paths(Path(td))
        config_store = ConfigStore(paths)
        config_store.save(AppConfig(port=8080))
        check(config_store.load().port == 8080, "config round trip")

        library_store = LibraryStore(paths)
        library_store.upsert(LocalModel(id="model-1", path="/tmp/model.gguf"))
        check(library_store.load()[0].id == "model-1", "library round trip")

        profile_store = ProfileStore(paths)
        profile_store.upsert(ModelProfile(id="profile-1", model_id="model-1", name="Default"))
        check(profile_store.list_for_model("model-1")[0].name == "Default", "profile round trip")

        # Phase 7: library scan
        scan_dir = Path(td) / "models"
        scan_dir.mkdir()
        (scan_dir / "test-Q4_K_M.gguf").write_bytes(b"\x00" * 1024)
        (scan_dir / "other-BF16.gguf").write_bytes(b"\x00" * 2048)
        (scan_dir / "not-a-model.txt").write_text("ignore me")

        # Scan with fresh library store so only scanned files appear.
        scan_paths = default_paths(Path(td) / "scan-data")
        scan_lib = LibraryStore(scan_paths)
        result = scan_library(scan_dir, scan_lib)
        check(isinstance(result, ScanResult), "scan result type")
        check(result.scanned_files == 2, f"scanned 2 gguf files, got {result.scanned_files}")
        check(result.added == 2, f"added 2 models, got {result.added}")
        check(result.removed == 0, f"removed 0, got {result.removed}")

        models = scan_lib.load()
        check(len(models) == 2, f"library has 2 scanned models, got {len(models)}")
        scanned = [m for m in models if m.path.startswith(str(scan_dir))]
        check(len(scanned) == 2, f"2 scanned models, got {len(scanned)}")
        quants = {m.quant for m in scanned}
        check("Q4_K_M" in quants, f"Q4_K_M quant inferred, got {quants}")
        check("BF16" in quants, f"BF16 quant inferred, got {quants}")
        sizes = {m.size_bytes for m in scanned}
        check(1024 in sizes, f"1024 byte file detected, got {sizes}")
        check(2048 in sizes, f"2048 byte file detected, got {sizes}")

        # Re-scan: should keep existing, not re-add.
        result2 = scan_library(scan_dir, scan_lib)
        check(result2.added == 0, f"re-scan added 0, got {result2.added}")
        check(result2.kept == 2, f"re-scan kept 2, got {result2.kept}")

        # Delete one file and re-scan: should remove stale entry.
        (scan_dir / "other-BF16.gguf").unlink()
        result3 = scan_library(scan_dir, scan_lib)
        check(result3.removed == 1, f"post-delete removed 1, got {result3.removed}")
        check(len(scan_lib.load()) == 1, f"library has 1 scanned model after removal, got {len(scan_lib.load())}")

        # infer_quant standalone
        check(infer_quant("model-Q8_0.gguf") == "Q8_0", "infer Q8_0")
        check(infer_quant("model-IQ3_S.gguf") == "IQ3_S", "infer IQ3_S")
        check(infer_quant("plain.gguf") is None, "no quant for plain filename")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
