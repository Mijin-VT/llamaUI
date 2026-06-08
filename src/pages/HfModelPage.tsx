import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AppConfig, ModelCardResponse, HfSibling, GgufFileInfo, SettingHint } from "../shared/types";
import {
  hfModelCard,
  hfModel,
  downloadStart,
  downloadCancel,
  onDownloadProgress,
  modelsList,
} from "../shared/tauriApi";

interface HfModelPageProps {
  repoId: string | null;
  config: AppConfig | null;
  onApplyHints: (hints: SettingHint[]) => void;
  onGoToRun: () => void;
}

interface DownloadState {
  filename: string;
  bytesDownloaded: number;
  bytesTotal: number | undefined;
  done: boolean;
  error?: string;
}

function basename(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx >= 0 ? path.slice(idx + 1) : path;
}
export default function HfModelPage({ repoId, config, onApplyHints, onGoToRun }: HfModelPageProps) {

  const [card, setCard] = useState<ModelCardResponse | null>(null);
  const [siblings, setSiblings] = useState<HfSibling[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloads, setDownloads] = useState<Record<string, DownloadState>>({});
  const [applyingSettings, setApplyingSettings] = useState(false);
  // Set of basenames of files already present on disk in models_dir
  const [localFiles, setLocalFiles] = useState<Set<string>>(new Set());

  // ── Fetch model card + file list when repo changes ────────────────────
  useEffect(() => {
    if (!repoId) {
      setCard(null);
      setSiblings([]);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([hfModelCard(repoId), hfModel(repoId)])
      .then(([cardResp, modelInfo]) => {
        if (cancelled) return;
        setCard(cardResp);
        setSiblings(modelInfo.siblings ?? []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [repoId]);

  // ── Listen for download progress ──────────────────────────────────────
  useEffect(() => {
    let unlisten: (() => void) | null = null;

    onDownloadProgress((progress) => {
      setDownloads((prev) => ({
        ...prev,
        [progress.filename]: {
          filename: progress.filename,
          bytesDownloaded: progress.bytes_downloaded,
          bytesTotal: progress.bytes_total,
          done: progress.done,
          error: progress.error,
        },
      }));
    }).then((fn) => {
      unlisten = fn;
    });

    return () => {
      unlisten?.();
    };
  }, []);

  // ── Refresh local file basenames so the FileRow can show a checkmark ──
  useEffect(() => {
    let cancelled = false;
    modelsList()
      .then((files: GgufFileInfo[]) => {
        if (cancelled) return;
        // modelsList returns paths like "Repo--Name/model.Q4.gguf"; the HF
        // API returns bare filenames. Compare basenames.
        setLocalFiles(new Set(files.map((f) => basename(f.rfilename))));
      })
      .catch(() => {
        // models_dir may not be configured — that's fine
      });
    return () => {
      cancelled = true;
    };
  }, [config?.models_dir]);

  // ── Helpers ───────────────────────────────────────────────────────────
  const formatBytes = useCallback((bytes?: number | null) => {
    if (bytes == null) return "—";
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
  }, []);

  const isMmproj = (name: string) => /^mmproj/i.test(name);
  const isGguf = (name: string) => name.toLowerCase().endsWith(".gguf");

  const ggufFiles = siblings.filter((s) => isGguf(s.rfilename));
  const mmprojFiles = ggufFiles.filter((s) => isMmproj(s.rfilename));
  const regularGguf = ggufFiles.filter((s) => !isMmproj(s.rfilename));

  const modelsDir = config?.models_dir;

  // ── Download handler ──────────────────────────────────────────────────
  const handleDownload = useCallback(
    async (filename: string) => {
      if (!repoId) return;
      if (!modelsDir) {
        setError("Set a models directory in Setup before downloading.");
        return;
      }

      // Mark as started
      setDownloads((prev) => ({
        ...prev,
        [filename]: { filename, bytesDownloaded: 0, bytesTotal: 0, done: false },
      }));

      try {
        await downloadStart(repoId, filename);
      } catch (err) {
        setDownloads((prev) => ({
          ...prev,
          [filename]: {
            ...prev[filename],
            done: true,
            error: err instanceof Error ? err.message : String(err),
          },
        }));
      }
    },
    [repoId, modelsDir],
  );

  const handleCancelDownload = useCallback(async (filename: string) => {
    try {
      await downloadCancel(repoId!, filename);
    } catch {
      // Best-effort cancel
    }
  }, [repoId]);
  // ── Apply settings: hand hints to App via callback, then go to Run ────
  const handleApplySettings = useCallback(() => {
    if (!card?.suggested_settings?.length) return;
    setApplyingSettings(true);
    onApplyHints(card.suggested_settings);
    onGoToRun();
    setApplyingSettings(false);
  }, [card, onApplyHints, onGoToRun]);

  // ── Empty state ───────────────────────────────────────────────────────
  if (!repoId) {
    return (
      <div className="page">
        <h2>Hugging Face Model Detail</h2>
        <p className="hint">Select a model from the Download page to view its details.</p>
      </div>
    );
  }

  // ── Loading state ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="page">
        <h2>{repoId}</h2>
        <p>Loading model details…</p>
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────
  if (error && !card) {
    return (
      <div className="page">
        <h2>{repoId}</h2>
        <div className="error-banner">Failed to load model details: {error}</div>
      </div>
    );
  }

  const cardData = card?.card_data;
  const hints = card?.suggested_settings ?? [];

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="page hf-model-page">
      <h2>{repoId}</h2>

      {/* ── Metadata panel ─────────────────────────────────────────────── */}
      <section className="hf-meta-panel">
        <h3>Model Information</h3>
        <dl className="meta-grid">
          {cardData?.pipeline_tag && (
            <>
              <dt>Pipeline</dt>
              <dd>{cardData.pipeline_tag}</dd>
            </>
          )}
          {cardData?.base_model && (
            <>
              <dt>Base Model</dt>
              <dd>{cardData.base_model}</dd>
            </>
          )}
          {cardData?.license && (
            <>
              <dt>License</dt>
              <dd>{cardData.license}</dd>
            </>
          )}
          {cardData?.model_type && (
            <>
              <dt>Model Type</dt>
              <dd>{cardData.model_type}</dd>
            </>
          )}
          {cardData?.library_name && (
            <>
              <dt>Library</dt>
              <dd>{cardData.library_name}</dd>
            </>
          )}
          {cardData?.language && cardData.language.length > 0 && (
            <>
              <dt>Languages</dt>
              <dd>{cardData.language.join(", ")}</dd>
            </>
          )}
          {(cardData?.tags?.length ?? 0) > 0 && (
            <>
              <dt>Tags</dt>
              <dd className="tag-list">
                {cardData!.tags!.map((t) => (
                  <span key={t} className="tag-badge">{t}</span>
                ))}
              </dd>
            </>
          )}
          {card?.repo_id && (
            <>
              <dt>Repository</dt>
              <dd>
                <a
                  href={`https://huggingface.co/${card.repo_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {card.repo_id}
                </a>
              </dd>
            </>
          )}
        </dl>
      </section>

      {/* ── GGUF files table ───────────────────────────────────────────── */}
      <section className="hf-files-section">
        <h3>GGUF Files</h3>
        {regularGguf.length === 0 && mmprojFiles.length === 0 ? (
          <p className="hint">No GGUF files found in this repository.</p>
        ) : (
          <table className="hf-files-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Type</th>
                <th>Size</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {regularGguf.map((s) => (
                <FileRow
                  key={s.rfilename}
                  sibling={s}
                  typeLabel="Model weights"
                  dlState={downloads[s.rfilename]}
                  isLocal={localFiles.has(basename(s.rfilename))}
                  modelsDir={modelsDir}
                  onDownload={handleDownload}
                  onCancel={handleCancelDownload}
                  formatBytes={formatBytes}
                />
              ))}
              {mmprojFiles.map((s) => (
                <FileRow
                  key={s.rfilename}
                  sibling={s}
                  typeLabel="Multimodal projector"
                  dlState={downloads[s.rfilename]}
                  isLocal={localFiles.has(basename(s.rfilename))}
                  modelsDir={modelsDir}
                  onDownload={handleDownload}
                  onCancel={handleCancelDownload}
                  formatBytes={formatBytes}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* ── Setting hints ──────────────────────────────────────────────── */}
      {hints.length > 0 && (
        <section className="hf-hints-section">
          <h3>Suggested Settings</h3>
          <p className="hint">
            These settings were detected from the model card and may improve
            performance or are required for correct behaviour.
          </p>
          <table className="hf-hints-table">
            <thead>
              <tr>
                <th>Setting</th>
                <th>Value</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {hints.map((h, i) => (
                <tr key={`${h.key}-${i}`}>
                  <td className="mono">{h.key}</td>
                  <td className="mono">{h.value}</td>
                  <td>
                    <span className="source-badge">{h.source}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            className="btn btn-primary"
            disabled={applyingSettings}
            onClick={handleApplySettings}
          >
            {applyingSettings ? "Applying…" : "Apply these settings"}
          </button>
        </section>
      )}

      {/* ── Model card README ──────────────────────────────────────────── */}
      {card?.readme && (
        <section className="hf-readme-section">
          <h3>Model Card</h3>
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {card.readme}
            </ReactMarkdown>
          </div>
        </section>
      )}

      {/* ── No readme fallback ─────────────────────────────────────────── */}
      {!card?.readme && !error && (
        <section className="hf-readme-section">
          <h3>Model Card</h3>
          <p className="hint">No README/model card available for this repository.</p>
        </section>
      )}

      {/* ── Non-blocking error banner ──────────────────────────────────── */}
      {error && card && (
        <div className="error-banner">
          Some data could not be loaded: {error}
        </div>
      )}
    </div>
  );
}

// ─── File row sub-component ───────────────────────────────────────────────

interface FileRowProps {
  sibling: HfSibling;
  typeLabel: string;
  dlState?: DownloadState;
  isLocal: boolean;
  modelsDir?: string;
  onDownload: (filename: string) => void;
  onCancel: (filename: string) => void;
  formatBytes: (bytes?: number | null) => string;
}

function FileRow({
  sibling,
  typeLabel,
  dlState,
  isLocal,
  modelsDir,
  onDownload,
  onCancel,
  formatBytes,
}: FileRowProps) {
  const name = sibling.rfilename;
  const active = dlState != null && !dlState.done;
  const done = (dlState?.done && !dlState.error) || isLocal;
  const failed = dlState?.done && !!dlState.error;

  const progressPct =
    dlState && dlState.bytesTotal != null && dlState.bytesTotal > 0
      ? Math.round((dlState.bytesDownloaded / dlState.bytesTotal) * 100)
      : 0;

  return (
    <tr className={failed ? "row-error" : done ? "row-done" : ""}>
      <td className="mono filename-cell" title={name}>
        {name}
      </td>
      <td>
        <span
          className={`type-badge ${
            typeLabel === "Multimodal projector" ? "type-mmproj" : "type-model"
          }`}
        >
          {typeLabel}
        </span>
      </td>
      <td>{formatBytes(sibling.size)}</td>
      <td className="action-cell">
        {!done && !active && !failed && (
          <button
            className="btn btn-sm"
            disabled={!modelsDir}
            title={
              modelsDir
                ? `Download to ${modelsDir}`
                : "Set a models directory in Setup first"
            }
            onClick={() => onDownload(name)}
          >
            Download
          </button>
        )}
        {active && (
          <div className="download-progress">
            <div className="progress-bar-track">
              <div
                className="progress-bar-fill"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <span className="progress-text">
              {formatBytes(dlState!.bytesDownloaded)} / {formatBytes(dlState!.bytesTotal)}{" "}
              ({progressPct}%)
            </span>
            <button className="btn btn-sm btn-danger" onClick={() => onCancel(name)}>
              Cancel
            </button>
          </div>
        )}
        {done && !active && (
          <span className="status-ok">Downloaded{isLocal && !dlState?.done ? " (local)" : ""}</span>
        )}
        {failed && (
          <span className="status-err" title={dlState!.error}>
            Failed
          </span>
        )}
      </td>
    </tr>
  );
}
