"""HuggingFace GGUF search and model metadata service."""
from __future__ import annotations

import concurrent.futures
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Iterable, List, Optional, Protocol

HF_API = "https://huggingface.co/api"
HF_WEB = "https://huggingface.co"
_QUANT_RE = re.compile(r"(?:^|[-_.])(Q\d(?:_[A-Z0-9]+)*(?:_[A-Z0-9]+)?|IQ\d_[A-Z0-9]+|F16|BF16|F32)(?:[-_.]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class HfFilter:
    key: str
    label: str
    values: List[str] = field(default_factory=list)

    def is_active(self) -> bool:
        return bool(self.values)


@dataclass(frozen=True)
class HfFile:
    name: str
    size_bytes: Optional[int] = None
    quantization: Optional[str] = None
    context_length: Optional[int] = None
    is_multimodal_projector: bool = False
    is_split: bool = False
    download_url: Optional[str] = None


@dataclass(frozen=True)
class HfRepoSummary:
    repo_id: str
    author: str
    downloads: int = 0
    likes: int = 0
    tags: List[str] = field(default_factory=list)
    gated: bool = False
    private: bool = False
    license: Optional[str] = None
    architecture: Optional[str] = None
    base_model: Optional[str] = None
    files: List[HfFile] = field(default_factory=list)
    hardware_fit: Optional[str] = None
    card_text: Optional[str] = None

    def total_size_bytes(self) -> int:
        return sum(f.size_bytes or 0 for f in self.files)


@dataclass(frozen=True)
class HfSearchOutcome:
    status: str
    repos: List[HfRepoSummary] = field(default_factory=list)
    message: Optional[str] = None

    @classmethod
    def empty(cls, message: str) -> "HfSearchOutcome":
        return cls(status="empty", message=message)

    @classmethod
    def error(cls, message: str) -> "HfSearchOutcome":
        return cls(status="error", message=message)

    @classmethod
    def ok(cls, repos: Iterable[HfRepoSummary]) -> "HfSearchOutcome":
        repos_list = list(repos)
        if not repos_list:
            return cls.empty("Search returned no GGUF models.")
        return cls(status="ok", repos=repos_list)


class HfSearchService(Protocol):
    def search(self, query: str, filters: Iterable[HfFilter]) -> HfSearchOutcome: ...


class HuggingFaceSearchService:
    def __init__(self, token: Optional[str] = None, timeout: float = 20.0, limit: int = 25):
        self.token = token
        self.timeout = timeout
        self.limit = limit

    def search(self, query: str, filters: Iterable[HfFilter] = ()) -> HfSearchOutcome:
        query = (query or "").strip()
        if not query:
            return HfSearchOutcome.empty("Enter a model search query.")
        try:
            repos = self._search_repos(query)
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                hydrated = list(pool.map(self._hydrate_repo, repos))
            return HfSearchOutcome.ok(repo for repo in hydrated if repo.files)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return HfSearchOutcome.error("HuggingFace authentication required or token rejected. Save a valid token in Settings.")
            if exc.code == 429:
                return HfSearchOutcome.error("HuggingFace rate limit reached. Try again later.")
            return HfSearchOutcome.error(f"HuggingFace HTTP {exc.code}: {exc.reason}")
        except Exception as exc:
            return HfSearchOutcome.error(str(exc))

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "llamaUI-qt/0.1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _json(self, url: str):
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _search_repos(self, query: str) -> list[dict]:
        params = urllib.parse.urlencode({
            "filter": "gguf",
            "search": query,
            "sort": "downloads",
            "direction": "-1",
            "limit": str(self.limit),
            "full": "true",
        })
        data = self._json(f"{HF_API}/models?{params}")
        return data if isinstance(data, list) else []

    def _detail(self, repo_id: str) -> dict:
        safe = urllib.parse.quote(repo_id, safe="/")
        data = self._json(f"{HF_API}/models/{safe}")
        return data if isinstance(data, dict) else {}

    def _tree(self, repo_id: str) -> list[dict]:
        safe = urllib.parse.quote(repo_id, safe="/")
        try:
            data = self._json(f"{HF_API}/models/{safe}/tree/main?recursive=true")
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _hydrate_repo(self, raw: dict) -> HfRepoSummary:
        repo_id = str(raw.get("modelId") or raw.get("id") or "")
        detail = raw
        siblings = raw.get("siblings") or []
        if not siblings or not any(str(s.get("rfilename", "")).lower().endswith(".gguf") for s in siblings):
            detail = {**raw, **self._detail(repo_id)}
        revision = str(detail.get("defaultBranch") or detail.get("default_branch") or "main")
        files = self._files(repo_id, detail, revision)
        if any(f.size_bytes is None for f in files):
            by_name = {str(item.get("path") or item.get("rfilename") or ""): item for item in self._tree(repo_id)}
            files = [self._with_tree_size(file, by_name.get(file.name)) for file in files]
        card_data = detail.get("cardData") or detail.get("card_data") or {}
        tags = [str(t) for t in detail.get("tags") or []]
        license_name = card_data.get("license") if isinstance(card_data, dict) else None
        base_model = card_data.get("base_model") if isinstance(card_data, dict) else None
        if isinstance(base_model, list):
            base_model = next((str(x) for x in base_model if x), None)
        architecture = None
        config = detail.get("config")
        if isinstance(config, dict):
            arch = config.get("architectures")
            architecture = config.get("model_type") or (arch[0] if isinstance(arch, list) and arch else None)
        return HfRepoSummary(
            repo_id=repo_id,
            author=str(detail.get("author") or repo_id.split("/", 1)[0]),
            downloads=int(detail.get("downloads") or 0),
            likes=int(detail.get("likes") or 0),
            tags=tags,
            gated=bool(detail.get("gated")),
            private=bool(detail.get("private")),
            license=str(license_name) if license_name else None,
            architecture=str(architecture) if architecture else None,
            base_model=str(base_model) if base_model else None,
            files=files,
            hardware_fit=self._hardware_fit(files),
            card_text=None,
        )

    def _files(self, repo_id: str, detail: dict, revision: str) -> list[HfFile]:
        out: list[HfFile] = []
        for sibling in detail.get("siblings") or []:
            name = str(sibling.get("rfilename") or sibling.get("path") or "")
            lower = name.lower()
            if not lower.endswith(".gguf") and "mmproj" not in lower:
                continue
            lfs = sibling.get("lfs") if isinstance(sibling.get("lfs"), dict) else {}
            size = sibling.get("size") or lfs.get("size")
            out.append(HfFile(
                name=name,
                size_bytes=int(size) if isinstance(size, int) else None,
                quantization=_quant(name),
                is_multimodal_projector="mmproj" in lower,
                is_split=_is_split(name),
                download_url=f"{HF_WEB}/{urllib.parse.quote(repo_id, safe='/')}/resolve/{urllib.parse.quote(revision, safe='')}/{urllib.parse.quote(name, safe='/')}",
            ))
        out.sort(key=lambda f: (f.is_multimodal_projector, f.name.lower()))
        return out

    def _with_tree_size(self, file: HfFile, tree_item: Optional[dict]) -> HfFile:
        if not tree_item:
            return file
        lfs = tree_item.get("lfs") if isinstance(tree_item.get("lfs"), dict) else {}
        size = tree_item.get("size") or lfs.get("size")
        return replace(file, size_bytes=size) if isinstance(size, int) else file

    def fetch_card_text(self, repo_id: str) -> Optional[str]:
        safe = urllib.parse.quote(repo_id, safe="/")
        try:
            req = urllib.request.Request(f"{HF_WEB}/{safe}/raw/main/README.md", headers=self._headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None


    def _hardware_fit(self, files: list[HfFile]) -> Optional[str]:
        sizes = [f.size_bytes for f in files if f.size_bytes and not f.is_multimodal_projector]
        if not sizes:
            return None
        return compute_hardware_fit(min(sizes))
def compute_hardware_fit(size_bytes: int | None) -> Optional[str]:
    if not size_bytes:
        return None
    vram = _detect_vram_bytes()
    ram = _detect_ram_bytes()
    if vram and size_bytes <= vram * 0.85:
        return "gpu-likely"
    if ram and size_bytes <= ram * 0.75:
        return "partial-gpu"
    return "unlikely"

    
class NotImplementedHfSearchService:
    def search(self, query: str, filters: Iterable[HfFilter] = ()) -> HfSearchOutcome:
        return HfSearchOutcome(status="not-implemented", message="HuggingFace search service is not configured.")


def _detect_ram_bytes() -> Optional[int]:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _detect_vram_bytes() -> Optional[int]:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except OSError:
        return None
    values = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            values.append(int(line) * 1024 * 1024)
    return max(values) if values else None


def _quant(name: str) -> Optional[str]:
    match = _QUANT_RE.search(name)
    return match.group(1).upper() if match else None


def _is_split(name: str) -> bool:
    lower = name.lower()
    return bool(re.search(r"-\d{5}-of-\d{5}\.gguf$", lower) or re.search(r"\.part\d+\.gguf$", lower))


_default_service: HfSearchService = HuggingFaceSearchService()


def get_search_service() -> HfSearchService:
    return _default_service


def set_search_service(service: HfSearchService) -> None:
    global _default_service
    _default_service = service



@dataclass(frozen=True)
class HfConnectivity:
    """Result of a lightweight HuggingFace API reachability probe."""
    reachable: bool
    latency_ms: Optional[float] = None
    status_detail: str = ""


def check_hf_connectivity(token: Optional[str] = None, timeout: float = 8.0) -> HfConnectivity:
    """Lightweight HEAD probe to ``huggingface.co/api/models``.

    Returns reachability, round-trip latency, and a human-readable detail string.
    """
    import time

    headers = {"User-Agent": "llamaUI-qt/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{HF_API}/models?limit=1"
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.monotonic() - t0) * 1000
        return HfConnectivity(
            reachable=True,
            latency_ms=round(elapsed, 1),
            status_detail=f"HTTP {resp.status}",
        )
    except urllib.error.HTTPError as exc:
        return HfConnectivity(
            reachable=False,
            status_detail=f"HTTP {exc.code} {exc.reason}",
        )
    except Exception as exc:
        return HfConnectivity(reachable=False, status_detail=str(exc)[:120])

__all__ = [
    "HfConnectivity",
    "HfFilter",
    "HfFile",
    "HfRepoSummary",
    "HfSearchOutcome",
    "HfSearchService",
    "HuggingFaceSearchService",
    "NotImplementedHfSearchService",
    "check_hf_connectivity",
    "compute_hardware_fit",
    "set_search_service",
]
