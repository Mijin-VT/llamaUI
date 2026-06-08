import { useState, useEffect, useCallback, useRef } from "react";
import {
  hfSearch,
  downloadStart,
  downloadCancel,
  onDownloadProgress,
  modelsList,
} from "../shared/tauriApi";
import type {
  AppConfig,
  HfSearchResult,
  DownloadProgress,
  GgufFileInfo,
} from "../shared/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface DownloadPageProps {
  config: AppConfig | null;
  onSelectRepo: (repoId: string) => void;
  onSelectModel: (modelPath: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number | undefined | null): string {
  if (bytes == null) return "—";
  const gib = bytes / (1024 * 1024 * 1024);
  if (gib >= 1) return `${gib.toFixed(2)} GiB`;
  const mib = bytes / (1024 * 1024);
  if (mib >= 1) return `${mib.toFixed(1)} MiB`;
  return `${(bytes / 1024).toFixed(0)} KiB`;
}

function downloadKey(repoId: string, filename: string): string {
  return `${repoId}::${filename}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DownloadPage({
  config,
  onSelectRepo,
  onSelectModel,
}: DownloadPageProps) {
  // Search state
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HfSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Expanded repo rows — which repos have their file list open
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Active downloads keyed by "repoId::filename"
  const [progress, setProgress] = useState<Map<string, DownloadProgress>>(
    new Map(),
  );

  // Already-downloaded local files (basenames) for checkmark display
  const [localFiles, setLocalFiles] = useState<Set<string>>(new Set());

  // Track the unlisten handle for download-progress events
  const unlistenRef = useRef<(() => void) | null>(null);

  // -----------------------------------------------------------------------
  // Refresh local file list so we can show checkmarks
  // -----------------------------------------------------------------------

  const refreshLocalFiles = useCallback(async () => {
    try {
      const files = await modelsList();
      // modelsList returns paths like "Repo--Name/model.Q4.gguf"; the HF API
      // returns bare filenames like "model.Q4.gguf". Compare basenames.
      setLocalFiles(
        new Set(
          files.map((f: GgufFileInfo) => {
            const name = f.rfilename;
            const idx = name.lastIndexOf("/");
            return idx >= 0 ? name.slice(idx + 1) : name;
          }),
        ),
      );
    } catch {
      // models_dir may not be configured yet — that's fine
    }
  }, []);

  // -----------------------------------------------------------------------
  // Listen for download progress events
  // -----------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    async function attach() {
      const unlisten = await onDownloadProgress((ev: DownloadProgress) => {
        if (cancelled) return;
        setProgress((prev) => {
          const next = new Map(prev);
          next.set(downloadKey(ev.repo_id, ev.filename), ev);
          return next;
        });
        // When a download finishes, refresh local files
        if (ev.done) {
          refreshLocalFiles();
        }
      });
      if (!cancelled) {
        unlistenRef.current = unlisten;
      } else {
        unlisten();
      }
    }

    attach();

    return () => {
      cancelled = true;
      unlistenRef.current?.();
      unlistenRef.current = null;
    };
  }, [refreshLocalFiles]);

  // -----------------------------------------------------------------------
  // Initial local file load
  // -----------------------------------------------------------------------

  useEffect(() => {
    refreshLocalFiles();
  }, [refreshLocalFiles]);

  // -----------------------------------------------------------------------
  // Search
  // -----------------------------------------------------------------------

  const doSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (trimmed.length === 0) return;
    setSearching(true);
    setSearchError(null);
    setResults([]);
    try {
      const res = await hfSearch(trimmed);
      setResults(res);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Search failed unexpectedly";
      setSearchError(msg);
    } finally {
      setSearching(false);
    }
  }, [query]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") doSearch();
    },
    [doSearch],
  );

  // -----------------------------------------------------------------------
  // Expand / collapse
  // -----------------------------------------------------------------------

  const toggleExpand = useCallback((repoId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(repoId)) next.delete(repoId);
      else next.add(repoId);
      return next;
    });
  }, []);

  // -----------------------------------------------------------------------
  // Download helpers
  // -----------------------------------------------------------------------

  const startDownload = useCallback(
    async (repoId: string, filename: string) => {
      if (!config?.models_dir) return;
      const key = downloadKey(repoId, filename);
      // Optimistically mark as in-progress
      setProgress((prev) => {
        const next = new Map(prev);
        next.set(key, {
          id: "",
          repo_id: repoId,
          filename,
          bytes_downloaded: 0,
          bytes_total: undefined,
          done: false,
        });
        return next;
      });
      try {
        await downloadStart(repoId, filename);
      } catch (err: unknown) {
        setProgress((prev) => {
          const next = new Map(prev);
          next.set(key, {
            id: "",
            repo_id: repoId,
            filename,
            bytes_downloaded: 0,
            bytes_total: undefined,
            done: true,
            error:
              err instanceof Error ? err.message : "Download failed to start",
          });
          return next;
        });
      }
    },
    [config?.models_dir],
  );

  const cancelDownload = useCallback(
    async (repoId: string, filename: string) => {
      try {
        await downloadCancel(repoId, filename);
      } catch {
        // ignore — may already be done / cancelled
      }
      setProgress((prev) => {
        const next = new Map(prev);
        next.delete(downloadKey(repoId, filename));
        return next;
      });
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Determine local path for a downloaded file
  // -----------------------------------------------------------------------

  function localPathFor(filename: string): string | null {
    if (!config?.models_dir) return null;
    return `${config.models_dir}/${filename}`;
  }

  // -----------------------------------------------------------------------
  // Tag badge
  // -----------------------------------------------------------------------

  function tagBadge(label: string, className: string) {
    return (
      <span key={label} className={`tag-badge ${className}`}>
        {label}
      </span>
    );
  }

  // -----------------------------------------------------------------------
  // Render file row
  // -----------------------------------------------------------------------

  function renderFile(repoId: string, file: GgufFileInfo) {
    const key = downloadKey(repoId, file.rfilename);
    const prog = progress.get(key);
    const isLocal = localFiles.has(file.rfilename);
    const isDownloading = prog != null && !prog.done;
    const hasError = prog?.error != null;
    const isDone = (prog != null && prog.done && !prog.error) || isLocal;

    const pct =
      prog?.bytes_total && prog.bytes_total > 0
        ? Math.round((prog.bytes_downloaded / prog.bytes_total) * 100)
        : null;

    return (
      <div key={file.rfilename} className="gguf-file-row">
        <div className="gguf-file-info">
          <span className="gguf-filename">{file.rfilename}</span>
          {file.size != null && (
            <span className="gguf-size">{formatBytes(file.size)}</span>
          )}
        </div>

        {/* Progress bar */}
        {isDownloading && (
          <div className="download-progress-bar-wrapper">
            <div
              className="download-progress-bar"
              style={{ width: `${pct ?? 0}%` }}
            />
            <span className="download-progress-text">
              {formatBytes(prog!.bytes_downloaded)}
              {prog!.bytes_total ? ` / ${formatBytes(prog!.bytes_total)}` : ""}
              {pct != null ? ` (${pct}%)` : ""}
            </span>
          </div>
        )}

        {/* Error */}
        {hasError && (
          <span className="download-error">{prog!.error}</span>
        )}

        {/* Actions */}
        <div className="gguf-file-actions">
          {isDone && (
            <>
              <span className="download-done">✓ Downloaded</span>
              {localPathFor(file.rfilename) && (
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() =>
                    onSelectModel(localPathFor(file.rfilename)!)
                  }
                >
                  Run this model
                </button>
              )}
            </>
          )}
          {isDownloading && (
            <button
              className="btn btn-sm btn-danger"
              onClick={() => cancelDownload(repoId, file.rfilename)}
            >
              Cancel
            </button>
          )}
          {!isDone && !isDownloading && !hasError && (
            <button
              className="btn btn-sm btn-primary"
              disabled={!config?.models_dir}
              title={
                config?.models_dir
                  ? "Download to models directory"
                  : "Set a models directory in Setup first"
              }
              onClick={() => startDownload(repoId, file.rfilename)}
            >
              Download
            </button>
          )}
          {hasError && (
            <button
              className="btn btn-sm btn-primary"
              disabled={!config?.models_dir}
              onClick={() => startDownload(repoId, file.rfilename)}
            >
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const noModelsDir = !config?.models_dir;

  return (
    <div className="page download-page">
      <h2>Download Models</h2>

      {noModelsDir && (
        <div className="callout callout-warn">
          Set a models directory in Setup before downloading.
        </div>
      )}

      {/* Search */}
      <div className="search-bar">
        <input
          type="text"
          className="search-input"
          placeholder="Search HuggingFace for GGUF models…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={searching}
        />
        <button
          className="btn btn-primary"
          onClick={doSearch}
          disabled={searching || query.trim().length === 0}
        >
          {searching ? "Searching…" : "Search HuggingFace"}
        </button>
      </div>

      {/* Errors */}
      {searchError && (
        <div className="callout callout-error">{searchError}</div>
      )}

      {/* Results */}
      {results.length === 0 && !searching && !searchError && query.trim().length > 0 && (
        <div className="empty-state">No results found.</div>
      )}

      <div className="search-results">
        {results.map((repo) => {
          const isExpanded = expanded.has(repo.id);
          return (
            <div key={repo.id} className="search-result-card">
              <div
                className="search-result-header"
                onClick={() => toggleExpand(repo.id)}
              >
                <div className="repo-id-row">
                  <button
                    className="repo-id-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectRepo(repo.id);
                    }}
                    title="View model details"
                  >
                    {repo.id}
                  </button>
                  <span className="expand-toggle">
                    {isExpanded ? "▾" : "▸"}
                  </span>
                </div>

                <div className="repo-meta">
                  <span title="Downloads">↓ {repo.downloads.toLocaleString()}</span>
                  <span title="Likes">♥ {repo.likes.toLocaleString()}</span>
                  {repo.gated && tagBadge("Gated", "badge-warn")}
                  {repo.private && tagBadge("Private", "badge-private")}
                </div>

                <div className="repo-tags">
                  {repo.tags.slice(0, 8).map((t) => (
                    <span key={t} className="tag-badge badge-default">
                      {t}
                    </span>
                  ))}
                  {repo.tags.length > 8 && (
                    <span className="tag-badge badge-muted">
                      +{repo.tags.length - 8}
                    </span>
                  )}
                </div>

                <div className="repo-file-count">
                  {repo.gguf_files.length} GGUF file
                  {repo.gguf_files.length !== 1 ? "s" : ""}
                </div>
              </div>

              {isExpanded && (
                <div className="gguf-files-list">
                  {repo.gguf_files.length === 0 && (
                    <div className="empty-state empty-state-sm">
                      No GGUF files listed.
                    </div>
                  )}
                  {repo.gguf_files.map((file) => renderFile(repo.id, file))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
