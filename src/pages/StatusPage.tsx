import { useState, useEffect, useCallback, useRef } from "react";
import type { AppConfig, ServerStatus as ServerStatusType } from "../shared/types";
import {
  serverStop,
  serverStatus,
  onServerLog,
  onServerStarted,
} from "../shared/tauriApi";

const MAX_LOG_LINES = 500;
const HEALTH_POLL_INTERVAL_MS = 5000;

interface StatusPageProps {
  config: AppConfig | null;
}

export default function StatusPage({ config }: StatusPageProps) {
  const [status, setStatus] = useState<ServerStatusType | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const autoScrollRef = useRef(true);
  const healthTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- Fetch current server status from backend ---
  const refreshStatus = useCallback(async () => {
    try {
      const s = await serverStatus();
      setStatus(s);
      // On first load after a page refresh, backfill logs from the backend snapshot
      if (logs.length === 0 && s.log_lines.length > 0) {
        setLogs(s.log_lines.slice(-MAX_LOG_LINES));
      }
    } catch (e) {
      setError(String(e));
    }
  }, [logs.length]);

  // --- Real-time log listener + server-started listener ---
  useEffect(() => {
    let unlistenLog: (() => void) | undefined;
    let unlistenStarted: (() => void) | undefined;

    onServerLog((line: string) => {
      setLogs((prev) => {
        const next = [...prev, line];
        return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
      });
    }).then((fn) => {
      unlistenLog = fn;
    });

    onServerStarted(() => {
      refreshStatus();
    }).then((fn) => {
      unlistenStarted = fn;
    });

    return () => {
      unlistenLog?.();
      unlistenStarted?.();
    };
  }, [refreshStatus]);

  // --- Health auto-poll while running ---
  useEffect(() => {
    if (healthTimerRef.current != null) {
      clearInterval(healthTimerRef.current);
      healthTimerRef.current = null;
    }
    if (!status?.running) return;
    const id = setInterval(() => {
      serverStatus()
        .then((s) => setStatus(s))
        .catch(() => {
          // ignore — next poll will retry
        });
    }, HEALTH_POLL_INTERVAL_MS);
    healthTimerRef.current = id;
    return () => {
      clearInterval(id);
    };
  }, [status?.running]);

  // --- Auto-scroll logs to bottom ---
  useEffect(() => {
    const el = logContainerRef.current;
    if (!el || !autoScrollRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  // --- Initial status fetch ---
  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  // --- Detect manual scroll to pause/resume auto-scroll ---
  const handleLogScroll = useCallback(() => {
    const el = logContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 20;
    autoScrollRef.current = atBottom;
  }, []);

  // --- Handlers ---
  const handleStop = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await serverStop();
      await refreshStatus();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [refreshStatus]);

  const handleClearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  // --- Derived values ---
  const running = status?.running ?? false;
  const health = status?.health; // "ok" | "loading" | "error" | undefined
  const pid = status?.pid;
  const command = status?.command;
  const startedAt = status?.started_at;
  const host = config?.host ?? "127.0.0.1";
  const port = config?.port ?? 8080;
  const serverUrl = `http://${host}:${port}`;

  // --- Health display label ---
  let healthLabel: string;
  let healthBadgeClass: string;
  if (!running) {
    healthLabel = "Stopped";
    healthBadgeClass = "badge badge-muted";
  } else if (health === "ok") {
    healthLabel = "Healthy";
    healthBadgeClass = "badge badge-success";
  } else if (health === "loading") {
    healthLabel = "Loading model…";
    healthBadgeClass = "badge badge-warning";
  } else if (health === "error") {
    healthLabel = "Error";
    healthBadgeClass = "badge badge-error";
  } else {
    // running but health is undefined/null — unreachable or not yet polled
    healthLabel = "Unreachable";
    healthBadgeClass = "badge badge-warning";
  }

  return (
    <div className="page status-page">
      <h2>Server Status</h2>

      {error && <div className="callout callout-error">{error}</div>}

      {/* --- Status overview --- */}
      <section className="card">
        <div className="card-body">
          <div className="status-row">
            <span className="status-label">State:</span>
            <span
              className={`badge ${running ? "badge-success" : "badge-muted"}`}
            >
              {running ? "Running" : "Stopped"}
            </span>
          </div>

          <div className="status-row">
            <span className="status-label">PID:</span>
            <span className="status-value mono">
              {pid != null ? pid : "—"}
            </span>
          </div>

          <div className="status-row">
            <span className="status-label">Started:</span>
            <span className="status-value">
              {startedAt ? new Date(startedAt).toLocaleString() : "—"}
            </span>
          </div>

          <div className="status-row">
            <span className="status-label">Health:</span>
            <span className={healthBadgeClass}>{healthLabel}</span>
          </div>

          {running && (
            <div className="status-row">
              <span className="status-label">Web UI:</span>
              <a href={serverUrl} target="_blank" rel="noopener noreferrer">
                {serverUrl}
              </a>
            </div>
          )}
        </div>
      </section>

      {/* --- Controls (no Start: the user starts the server from the Run page) --- */}
      <section className="flex-row" style={{ gap: 12, marginBottom: 16 }}>
        {running && (
          <button
            className="danger"
            onClick={handleStop}
            disabled={loading}
          >
            {loading ? "Stopping…" : "Stop Server"}
          </button>
        )}
        <button
          className="secondary"
          onClick={refreshStatus}
          disabled={loading}
        >
          Refresh
        </button>
        {!running && (
          <span className="hint">
            To start a model, go to the <strong>Run</strong> page and pick a
            model.
          </span>
        )}
      </section>

      {/* --- Generated command --- */}
      {command && (
        <section className="card">
          <header className="card-header">
            <h3>Generated Command</h3>
          </header>
          <div className="card-body">
            <pre className="command-preview mono">{command}</pre>
          </div>
        </section>
      )}

      {/* --- Logs --- */}
      <section className="card">
        <div className="card-header flex-row" style={{ justifyContent: "space-between" }}>
          <h3>Logs</h3>
          <button className="secondary btn-sm" onClick={handleClearLogs}>
            Clear
          </button>
        </div>
        <div className="card-body">
          <pre
            className="log-viewer"
            ref={logContainerRef}
            onScroll={handleLogScroll}
          >
            {logs.length === 0
              ? "(no logs yet)"
              : logs.map((line, i) => (
                  <div key={i} className="log-line">
                    {line}
                  </div>
                ))}
          </pre>
        </div>
      </section>
    </div>
  );
}
