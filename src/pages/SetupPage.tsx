import { useState, useEffect, useCallback } from "react";
import type { AppConfig, HardwareInfo } from "../shared/types";
import {
  pickLlamaServerExecutable,
  pickModelsDir,
  hfValidateToken,
  hfWhoami,
  hardwareScan,
  updateConfig,
} from "../shared/tauriApi";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const val = bytes / Math.pow(1024, i);
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function tokenSourceLabel(source: AppConfig["hf_token_source"]): string {
  if (source === "none") return "No token";
  if (source === "env_var") return "Detected HF_TOKEN env var";
  if (typeof source === "object" && "saved" in source) return "Saved token";
  return "No token";
}

function tokenSourceBadgeClass(source: AppConfig["hf_token_source"]): string {
  if (source === "env_var") return "badge badge-success";
  if (typeof source === "object" && "saved" in source) return "badge badge-info";
  return "badge badge-muted";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SetupPageProps {
  config: AppConfig | null;
  onConfigUpdate: (c: AppConfig) => void;
}

export default function SetupPage({ config, onConfigUpdate }: SetupPageProps) {
  // Local form state — synced from config prop
  const [serverPath, setServerPath] = useState(config?.llama_server_path ?? "");
  const [modelsDir, setModelsDir] = useState(config?.models_dir ?? "");
  const [host, setHost] = useState(config?.host ?? "127.0.0.1");
  const [port, setPort] = useState(config?.port ?? 8080);
  const [tokenSource, setTokenSource] = useState<AppConfig["hf_token_source"]>(
    config?.hf_token_source ?? "none",
  );
  const [tokenInput, setTokenInput] = useState("");
  const [whoamiResult, setWhoamiResult] = useState<string | null>(null);
  const [whoamiError, setWhoamiError] = useState<string | null>(null);

  // Hardware
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);

  // UI state
  const [loading, setLoading] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Sync from config prop when it changes externally
  useEffect(() => {
    if (!config) return;
    setServerPath(config.llama_server_path ?? "");
    setModelsDir(config.models_dir ?? "");
    setHost(config.host ?? "127.0.0.1");
    setPort(config.port ?? 8080);
    setTokenSource(config.hf_token_source ?? "none");
  }, [config]);

  // ---- Browse: llama-server executable ----
  const handleBrowseServer = useCallback(async () => {
    setLoading("browse-server");
    try {
      const path = await pickLlamaServerExecutable();
      if (path) setServerPath(path);
    } catch (e: unknown) {
      console.error("Failed to pick executable:", e);
    } finally {
      setLoading(null);
    }
  }, []);

  // ---- Browse: models directory ----
  const handleBrowseModelsDir = useCallback(async () => {
    setLoading("browse-dir");
    try {
      const dir = await pickModelsDir();
      if (dir) setModelsDir(dir);
    } catch (e: unknown) {
      console.error("Failed to pick models dir:", e);
    } finally {
      setLoading(null);
    }
  }, []);

  const buildConfig = useCallback(
    (nextTokenSource: AppConfig["hf_token_source"] = tokenSource): AppConfig => ({
      llama_server_path: serverPath || undefined,
      models_dir: modelsDir || undefined,
      host,
      port,
      hf_token_source: nextTokenSource,
      global_defaults: config?.global_defaults,
    }),
    [serverPath, modelsDir, host, port, tokenSource, config?.global_defaults],
  );

  const persistConfig = useCallback(
    async (nextConfig: AppConfig) => {
      await updateConfig(nextConfig);
      onConfigUpdate(nextConfig);
    },
    [onConfigUpdate],
  );

  // ---- Validate token ----
  const handleValidateToken = useCallback(async () => {
    setWhoamiResult(null);
    setWhoamiError(null);
    setLoading("validate-token");
    try {
      const typedToken = tokenInput.trim();
      const savedToken =
        typeof tokenSource === "object" && "saved" in tokenSource
          ? tokenSource.saved
          : null;
      const username = typedToken
        ? await hfValidateToken(typedToken)
        : savedToken
          ? await hfValidateToken(savedToken)
          : await hfWhoami();

      if (username) {
        setWhoamiResult(username);
      } else {
        setWhoamiError("No Hugging Face token is configured.");
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setWhoamiError(msg || "Token validation failed.");
    } finally {
      setLoading(null);
    }
  }, [tokenInput, tokenSource]);

  // ---- Save token ----
  const handleSaveToken = useCallback(async () => {
    const savedToken = tokenInput.trim();
    if (!savedToken) return;

    const nextTokenSource: AppConfig["hf_token_source"] = { saved: savedToken };
    setSaveError(null);
    setLoading("save-token");
    try {
      const nextConfig = buildConfig(nextTokenSource);
      await persistConfig(nextConfig);
      setTokenSource(nextTokenSource);
      setTokenInput("");
      setWhoamiResult(null);
      setWhoamiError(null);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setSaveError(msg || "Failed to save Hugging Face token.");
    } finally {
      setLoading(null);
    }
  }, [tokenInput, buildConfig, persistConfig]);

  // ---- Clear saved token ----
  const handleClearToken = useCallback(async () => {
    setSaveError(null);
    setLoading("clear-token");
    try {
      const nextConfig = buildConfig("none");
      await persistConfig(nextConfig);
      setTokenSource("none");
      setTokenInput("");
      setWhoamiResult(null);
      setWhoamiError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setSaveError(msg || "Failed to clear Hugging Face token.");
    } finally {
      setLoading(null);
    }
  }, [buildConfig, persistConfig]);

  // ---- Scan hardware ----
  const handleScanHardware = useCallback(async () => {
    setLoading("scan-hardware");
    try {
      const hw = await hardwareScan();
      setHardware(hw);
    } catch (e: unknown) {
      console.error("Hardware scan failed:", e);
    } finally {
      setLoading(null);
    }
  }, []);

  // ---- Save config ----
  const handleSave = useCallback(async () => {
    setSaveError(null);
    setSaveSuccess(false);
    setLoading("save");
    try {
      const newConfig = buildConfig();
      await persistConfig(newConfig);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setSaveError(msg || "Failed to save configuration.");
    } finally {
      setLoading(null);
    }
  }, [buildConfig, persistConfig]);

  // ---- Port input handler (int-only) ----
  const handlePortChange = useCallback((value: string) => {
    const n = parseInt(value, 10);
    setPort(isNaN(n) ? 0 : n);
  }, []);

  return (
    <div className="page">
      <h2>Setup</h2>

      {/* ---- Executable ---- */}
      <section className="card">
        <header className="card-header">
          <h3>llama-server Executable</h3>
        </header>
        <div className="card-body">
          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Path</label>
              <input
                type="text"
                value={serverPath}
                onChange={(e) => setServerPath(e.target.value)}
                placeholder="Path to llama-server binary"
              />
            </div>
            <div className="form-group">
              <button
                className="secondary"
                disabled={loading === "browse-server"}
                onClick={handleBrowseServer}
              >
                {loading === "browse-server" ? "…" : "Browse"}
              </button>
            </div>
          </div>
          {!serverPath && (
            <p className="hint">
              Select the llama-server binary. This is required to launch models.
            </p>
          )}
        </div>
      </section>

      {/* ---- Models directory ---- */}
      <section className="card">
        <header className="card-header">
          <h3>Model Download Directory</h3>
        </header>
        <div className="card-body">
          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Directory</label>
              <input
                type="text"
                value={modelsDir}
                onChange={(e) => setModelsDir(e.target.value)}
                placeholder="Directory for downloaded GGUF files"
              />
            </div>
            <div className="form-group">
              <button
                className="secondary"
                disabled={loading === "browse-dir"}
                onClick={handleBrowseModelsDir}
              >
                {loading === "browse-dir" ? "…" : "Browse"}
              </button>
            </div>
          </div>
          {!modelsDir && (
            <p className="hint">
              Choose a folder where downloaded models will be stored.
            </p>
          )}
        </div>
      </section>

      {/* ---- HF Token ---- */}
      <section className="card">
        <header className="card-header">
          <h3>Hugging Face Token</h3>
        </header>
        <div className="card-body">
          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Token source</label>
              <span className={tokenSourceBadgeClass(tokenSource)}>
                {tokenSourceLabel(tokenSource)}
              </span>
            </div>
            {tokenSource !== "none" && (
              <div className="form-group">
                <button className="secondary btn-sm" disabled={loading === "clear-token"} onClick={handleClearToken}>
                  Clear
                </button>
              </div>
            )}
          </div>

          <div className="form-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>New token</label>
              <input
                type="password"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="hf_xxxxxxxx (optional)"
              />
            </div>
            <div className="form-group">
              <button
                className="primary btn-sm"
                disabled={!tokenInput.trim() || loading === "save-token"}
                onClick={handleSaveToken}
              >
                {loading === "save-token" ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <button
                className="secondary btn-sm"
                disabled={loading === "validate-token"}
                onClick={handleValidateToken}
              >
                {loading === "validate-token" ? "Validating…" : "Validate Token"}
              </button>
            </div>
            {whoamiResult && (
              <span className="text-success">
                Authenticated as <strong>{whoamiResult}</strong>
              </span>
            )}
            {whoamiError && <span className="text-error">{whoamiError}</span>}
          </div>

          <p className="hint">
            A token is optional but needed for gated models or higher rate
            limits. If the <code>HF_TOKEN</code> environment variable is set, it
            will be detected automatically.
          </p>
        </div>
      </section>

      {/* ---- Connection ---- */}
      <section className="card">
        <header className="card-header">
          <h3>Connection Settings</h3>
        </header>
        <div className="card-body">
          <div className="form-row">
            <div className="form-group">
              <label>Host</label>
              <input
                type="text"
                value={host}
                onChange={(e) => setHost(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label>Port</label>
              <input
                type="number"
                min={1}
                max={65535}
                value={port}
                onChange={(e) => handlePortChange(e.target.value)}
              />
            </div>
          </div>
        </div>
      </section>

      {/* ---- Hardware ---- */}
      <section className="card">
        <header className="card-header">
          <h3>Hardware</h3>
        </header>
        <div className="card-body">
          <button
            className="secondary"
            disabled={loading === "scan-hardware"}
            onClick={handleScanHardware}
          >
            {loading === "scan-hardware" ? "Scanning…" : "Scan Hardware"}
          </button>

          {hardware && (
            <>
              <dl className="hw-grid">
                <dt>CPU</dt>
                <dd className="mono">{hardware.cpu_model}</dd>
                <dt>Cores / Threads</dt>
                <dd>
                  {hardware.cpu_cores} cores, {hardware.cpu_threads} threads
                </dd>
                <dt>RAM</dt>
                <dd>
                  {formatBytes(hardware.ram_total_bytes)} total,{" "}
                  {formatBytes(hardware.ram_available_bytes)} available
                </dd>
              </dl>

              {hardware.gpus.length > 0 && (
                <div>
                  <strong>GPUs</strong>
                  <table className="file-table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>VRAM Total</th>
                        <th>VRAM Free</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hardware.gpus.map((gpu, i) => (
                        <tr key={i}>
                          <td>{gpu.name}</td>
                          <td>{formatBytes(gpu.vram_total_bytes)}</td>
                          <td>{formatBytes(gpu.vram_free_bytes)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {hardware.llama_devices.length > 0 && (
                <div>
                  <strong>llama.cpp Devices</strong>
                  <table className="file-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>VRAM Total</th>
                        <th>VRAM Free</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hardware.llama_devices.map((dev) => (
                        <tr key={dev.index}>
                          <td>{dev.index}</td>
                          <td>{dev.name}</td>
                          <td>
                            {dev.vram_total_bytes != null
                              ? formatBytes(dev.vram_total_bytes)
                              : "—"}
                          </td>
                          <td>
                            {dev.vram_free_bytes != null
                              ? formatBytes(dev.vram_free_bytes)
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </section>

      {/* ---- Save ---- */}
      {saveError && <div className="callout callout-error">{saveError}</div>}
      <div className="flex-row" style={{ justifyContent: "flex-end" }}>
        {saveSuccess && (
          <span className="text-success">Configuration saved.</span>
        )}
        <button
          className="primary btn-lg"
          disabled={loading === "save"}
          onClick={handleSave}
        >
          {loading === "save" ? "Saving…" : "Save Configuration"}
        </button>
      </div>
    </div>
  );
}
