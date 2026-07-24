"""Library scan service: scan configured models directory for GGUF files.

Companion-file detection is **filename-based only** — we do not inspect
the GGUF header. A user who renames ``mmproj-llava.gguf`` to
``llava-q4.gguf`` will see it appear as a runnable model. The Settings
page exposes a "Show companion files" toggle for users who want to
manage these files alongside their primary models.

Adding GGUF-header inspection (reading ``general.file_type`` from the
metadata) would improve accuracy but is out of scope here.
"""

from __future__ import annotations
import logging
import os
import re
import subprocess
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional
from llama_data import AppConfig, ConfigStore, LibraryStore, LocalModel

logger = logging.getLogger(__name__)

# Reuse the same quant-detection regex as the HF service.
_QUANT_RE = re.compile(
    r"(?:^|[-_.])(Q\d(?:_[A-Z0-9]+)*(?:_[A-Z0-9]+)?|IQ\d_[A-Z0-9]+|F16|BF16|F32)(?:[-_.]|$)",
    re.IGNORECASE,
)


def infer_quant(filename: str) -> Optional[str]:
    """Infer quantization type from a GGUF filename."""
    match = _QUANT_RE.search(filename)
    return match.group(1).upper() if match else None


# Substrings that identify companion / non-runnable GGUF files.
_COMPANION_PREFIXES = (
    "mmproj-", "mmproj.",
    "text-encoder-", "text-encoder.",
    "vision-encoder-", "vision-encoder.",
)


def _is_companion_name(lower_name: str) -> bool:
    """True if *lower_name* (already lowercased) matches a companion GGUF pattern."""
    for prefix in _COMPANION_PREFIXES:
        if prefix in lower_name:
            return True
    # "embedding" substring, but NOT when preceded by "_".
    if "embedding" in lower_name:
        idx = 0
        while True:
            pos = lower_name.find("embedding", idx)
            if pos == -1:
                break
            if pos == 0 or lower_name[pos - 1] != "_":
                return True
            idx = pos + len("embedding")
    return False


def is_companion_gguf(path: Path) -> bool:
    """True for mmproj, text-encoder, vision-encoder, and embedding GGUFs."""
    return _is_companion_name(path.name.lower())

def _companions_for_path(path: Path) -> list[str]:
    """Return all companion GGUF and .bin files in the same directory as *path*."""
    out: list[str] = []
    try:
        for child in path.parent.iterdir():
            suf = child.suffix.lower()
            name = child.name.lower()
            if suf == ".gguf" and is_companion_gguf(child):
                out.append(str(child.resolve()))
            elif suf == ".bin" and child.resolve() != path.resolve():
                out.append(str(child.resolve()))
    except OSError:
        pass
    out.sort()
    return out


def _mmproj_for_path(path: Path) -> Optional[str]:
    """Return the first mmproj / vision companion file (.gguf or .bin) in the same directory."""
    try:
        for child in path.parent.iterdir():
            name = child.name.lower()
            suf = child.suffix.lower()
            if (name.startswith("mmproj") or "vision" in name or "mmproj" in name) and suf in (".gguf", ".bin"):
                return str(child.resolve())
    except OSError:
        pass
    return None


def _bin_config_for_path(path: Path) -> Optional[str]:
    """Return the first .bin parameter config file in the same directory."""
    try:
        for child in path.parent.iterdir():
            name = child.name.lower()
            suf = child.suffix.lower()
            if suf == ".bin" and not (name.startswith("mmproj") or "vision" in name or "mmproj" in name):
                return str(child.resolve())
    except OSError:
        pass
    return None


def parse_bin_config(bin_path: Path) -> dict[str, Any]:
    """Parse parameter settings or CLI flags from a folder's .bin configuration file."""
    if not bin_path.exists() or not bin_path.is_file():
        return {}

    parsed_settings: dict[str, Any] = {}
    try:
        content = bin_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return {}

        # If JSON formatted
        if content.startswith("{") and content.endswith("}"):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # Parse CLI style flags (e.g. --ctx-size 8192 --n-gpu-layers 33 --temp 0.7)
        import re
        tokens = re.split(r"\s+", content)
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in ("-c", "--ctx-size", "--ctx_size"):
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    parsed_settings["ctx-size"] = int(tokens[i + 1])
                    i += 1
            elif tok in ("-ngl", "--n-gpu-layers", "--n_gpu_layers", "--gpu-layers"):
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    parsed_settings["n-gpu-layers"] = int(tokens[i + 1])
                    i += 1
            elif tok in ("--temp", "--temperature"):
                if i + 1 < len(tokens):
                    try:
                        parsed_settings["temp"] = float(tokens[i + 1])
                    except ValueError:
                        pass
                    i += 1
            elif tok in ("-t", "--threads"):
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    parsed_settings["threads"] = int(tokens[i + 1])
                    i += 1
            elif tok in ("--mmproj", "--vision"):
                if i + 1 < len(tokens):
                    parsed_settings["mmproj"] = tokens[i + 1]
                    i += 1
            i += 1
    except Exception as err:
        logger.debug("Failed to parse .bin config %s: %s", bin_path, err)

    return parsed_settings



def _is_primary_runnable_gguf(path: Path) -> bool:
    name = path.name.lower()
    if re.search(r"-\d{5}-of-\d{5}\.gguf$", name):
        return name.endswith("-00001-of-0000" + name.split("-of-")[-1][0] + ".gguf") if False else name.endswith("-00001-of-00001.gguf") or "-00001-of-" in name
    if re.search(r"\.part\d+\.gguf$", name):
        return ".part1.gguf" in name or ".part01.gguf" in name or ".part001.gguf" in name
    if _is_companion_name(name):
        return False
    return True


@dataclass(frozen=True)
class ScanResult:
    """Summary of a library scan operation."""
    scanned_files: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    kept: int = 0
    error: Optional[str] = None

    @property
    def total_models(self) -> int:
        return self.added + self.updated + self.kept


def scan_library(
    models_dir: Path,
    library: LibraryStore,
) -> ScanResult:
    """Scan *models_dir* for ``.gguf`` files and upsert into *library*."""
    try:
        models_dir = models_dir.expanduser().resolve()
    except Exception as err:
        return ScanResult(error=f"Ruta no válida: {err}")

    if not models_dir.is_dir():
        logger.warning("Models directory does not exist: %s", models_dir)
        return ScanResult(error=f"La carpeta no existe: {models_dir}")

    try:
        # Collect all complete .gguf files on disk.
        disk_files: dict[str, Path] = {}  # resolved path -> Path
        for gguf in models_dir.rglob("*.gguf"):
            if not _is_primary_runnable_gguf(gguf):
                continue
            try:
                resolved = gguf.resolve()
                disk_files[str(resolved)] = resolved
            except Exception:
                continue

        # Load existing library entries.
        existing = {m.id: m for m in library.load()}

        added = 0
        updated = 0
        kept = 0

        for resolved_str, resolved_path in disk_files.items():
            size_bytes: Optional[int] = None
            try:
                size_bytes = resolved_path.stat().st_size
            except OSError:
                pass

            filename = resolved_path.name
            quant = infer_quant(filename)
            companions = _companions_for_path(resolved_path)
            mmproj = _mmproj_for_path(resolved_path)
            bin_cfg = _bin_config_for_path(resolved_path)

            if resolved_str in existing:
                old = existing[resolved_str]
                updates: dict = {}
                if old.size_bytes != size_bytes:
                    updates["size_bytes"] = size_bytes
                if old.quant != quant and quant is not None:
                    updates["quant"] = quant
                if old.companion_paths != companions:
                    updates["companion_paths"] = companions
                if old.mmproj_path != mmproj:
                    updates["mmproj_path"] = mmproj
                if getattr(old, "bin_config_path", None) != bin_cfg:
                    updates["bin_config_path"] = bin_cfg
                if updates:
                    from dataclasses import asdict
                    fields = asdict(old)
                    fields.update(updates)
                    fields["updated_at"] = LocalModel.__dataclass_fields__["updated_at"].default_factory()
                    existing[resolved_str] = LocalModel(**fields)
                    updated += 1
                else:
                    kept += 1
            else:
                model = LocalModel(
                    id=resolved_str,
                    path=str(resolved_path),
                    size_bytes=size_bytes,
                    quant=quant,
                    companion_paths=companions,
                    mmproj_path=mmproj,
                    bin_config_path=bin_cfg,
                )
                existing[resolved_str] = model
                added += 1


        # Remove stale entries: those whose path is under models_dir but file is gone.
        removed = 0
        to_keep: dict[str, LocalModel] = {}
        for mid, model in existing.items():
            try:
                model_path = Path(model.path).resolve()
                model_path_resolved = str(model_path)
                try:
                    under_models_dir = model_path.is_relative_to(models_dir)
                except ValueError:
                    under_models_dir = False
                if under_models_dir and model_path_resolved not in disk_files:
                    removed += 1
                else:
                    to_keep[mid] = model
            except Exception:
                to_keep[mid] = model

        library.save(to_keep.values())

        result = ScanResult(
            scanned_files=len(disk_files),
            added=added,
            updated=updated,
            removed=removed,
            kept=kept,
        )
        logger.info(
            "Library scan complete: %d files, %d added, %d updated, %d removed, %d kept",
            result.scanned_files, result.added, result.updated, result.removed, result.kept,
        )
        return result
    except Exception as err:
        logger.error("Scan library error: %s", err, exc_info=True)
        return ScanResult(error=str(err))


def scan_models_dir(config: ConfigStore, library: LibraryStore) -> ScanResult:
    """High-level scan: read models_dir from config, run scan, return result.

    If models_dir is not configured or does not exist, returns an error result.
    """
    cfg = config.load()
    models_dir = cfg.models_dir
    if not models_dir:
        return ScanResult(error="Carpeta de modelos no configurada.")
    return scan_library(Path(models_dir), library)



def read_card_cache(card_cache_path: Optional[str]) -> Optional[str]:
    """Read a cached model card markdown file. Returns None if missing."""
    if not card_cache_path:
        return None
    path = Path(card_cache_path)
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def reveal_file(path: str) -> None:
    """Open the system file manager pointing at *path*."""
    p = Path(path)
    if not p.exists():
        return
    try:
        if os.name == "posix":
            subprocess.Popen(
                ["xdg-open", str(p.parent)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open(str(p.parent))
    except OSError:
        logger.debug("Failed to reveal file: %s", path, exc_info=True)


def open_hf(hf_repo: Optional[str]) -> None:
    """Open the HuggingFace model page in the system browser."""
    if not hf_repo:
        return
    url = f"https://huggingface.co/{hf_repo}"
    try:
        webbrowser.open(url)
    except OSError:
        logger.debug("Failed to open HF page: %s", url, exc_info=True)


from typing import Callable


@dataclass
class CustomScanOptions:
    target_dir: Path
    recursive: bool = True
    include_hidden: bool = False
    max_depth: int = 12
    excluded_dirs: list[str] = field(
        default_factory=lambda: ["node_modules", ".git", "__pycache__", "venv", "env", "dist"]
    )
    min_size_mb: float = 5.0


@dataclass
class CustomScanProgress:
    scanned_files: int = 0
    primary_models_found: int = 0
    companion_files_found: int = 0
    current_folder: str = ""


def scan_custom_folder(
    options: CustomScanOptions,
    library: LibraryStore,
    progress_callback: Optional[Callable[[CustomScanProgress], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> ScanResult:
    """Recursively scan a custom folder for GGUF models with options and merge into library.

    Options control depth, hidden items, folder exclusions, minimum file size, and recursion.
    Invokes progress_callback(progress) periodically.
    Checks cancel_check() to abort early if requested.
    """
    target = options.target_dir.expanduser().resolve()
    if not target.is_dir():
        return ScanResult(error=f"Directory not found: {target}")

    excluded_set = {d.strip().lower() for d in options.excluded_dirs if d.strip()}
    min_bytes = int(options.min_size_mb * 1024 * 1024)

    progress = CustomScanProgress(current_folder=str(target))
    discovered_primaries: dict[str, Path] = {}

    def _walk(curr_dir: Path, current_depth: int) -> None:
        if cancel_check and cancel_check():
            return
        if current_depth > options.max_depth:
            return

        progress.current_folder = str(curr_dir)
        if progress_callback:
            progress_callback(progress)

        try:
            entries = list(curr_dir.iterdir())
        except OSError:
            return

        subdirs: list[Path] = []
        for entry in entries:
            if cancel_check and cancel_check():
                return

            name = entry.name
            is_hidden = name.startswith(".")
            if is_hidden and not options.include_hidden:
                continue

            if entry.is_dir():
                if name.lower() in excluded_set:
                    continue
                if options.recursive:
                    subdirs.append(entry)
            elif entry.is_file():
                if name.lower().endswith(".gguf"):
                    progress.scanned_files += 1
                    try:
                        sz = entry.stat().st_size
                    except OSError:
                        sz = 0

                    if sz < min_bytes:
                        continue

                    if is_companion_gguf(entry):
                        progress.companion_files_found += 1
                    elif _is_primary_runnable_gguf(entry):
                        progress.primary_models_found += 1
                        resolved = entry.resolve()
                        discovered_primaries[str(resolved)] = resolved

                    if progress_callback and progress.scanned_files % 5 == 0:
                        progress_callback(progress)

        for sub in subdirs:
            if cancel_check and cancel_check():
                return
            _walk(sub, current_depth + 1)

    _walk(target, 0)

    if progress_callback:
        progress_callback(progress)

    # Merge into existing library entries (DO NOT DELETE existing entries from other folders)
    existing = {m.id: m for m in library.load()}
    added = 0
    updated = 0
    kept = 0

    for resolved_str, resolved_path in discovered_primaries.items():
        size_bytes: Optional[int] = None
        try:
            size_bytes = resolved_path.stat().st_size
        except OSError:
            pass

        filename = resolved_path.name
        quant = infer_quant(filename)
        companions = _companions_for_path(resolved_path)
        mmproj = _mmproj_for_path(resolved_path)
        bin_cfg = _bin_config_for_path(resolved_path)

        if resolved_str in existing:
            old = existing[resolved_str]
            updates: dict = {}
            if old.size_bytes != size_bytes:
                updates["size_bytes"] = size_bytes
            if old.quant != quant and quant is not None:
                updates["quant"] = quant
            if old.companion_paths != companions:
                updates["companion_paths"] = companions
            if old.mmproj_path != mmproj:
                updates["mmproj_path"] = mmproj
            if getattr(old, "bin_config_path", None) != bin_cfg:
                updates["bin_config_path"] = bin_cfg

            if updates:
                from dataclasses import asdict
                fields = asdict(old)
                fields.update(updates)
                fields["updated_at"] = LocalModel.__dataclass_fields__["updated_at"].default_factory()
                existing[resolved_str] = LocalModel(**fields)
                updated += 1
            else:
                kept += 1
        else:
            model = LocalModel(
                id=resolved_str,
                path=str(resolved_path),
                size_bytes=size_bytes,
                quant=quant,
                companion_paths=companions,
                mmproj_path=mmproj,
                bin_config_path=bin_cfg,
            )
            existing[resolved_str] = model
            added += 1


    library.save(existing.values())

    return ScanResult(
        scanned_files=progress.scanned_files,
        added=added,
        updated=updated,
        removed=0,
        kept=kept,
    )


__all__ = [
    "CustomScanOptions",
    "CustomScanProgress",
    "ScanResult",
    "infer_quant",
    "is_companion_gguf",
    "open_hf",
    "read_card_cache",
    "reveal_file",
    "scan_custom_folder",
    "scan_library",
    "scan_models_dir",
]

