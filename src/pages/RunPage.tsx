import { useState, useEffect, useCallback, useMemo } from "react";
import {
  modelsList,
  modelProfileList,
  modelProfileSave,
  modelRecommendation,
  serverStart,
  serverStop,
  serverStatus,
  hardwareScan,
} from "../shared/tauriApi";
import type {
  AppConfig,
  GgufFileInfo,
  LlamaSettings,
  ModelProfile,
  ModelRecommendation,
  HardwareInfo,
  ServerStatus,
  FitStatus,
  SettingHint,
} from "../shared/types";
import { LLAMA_OPTIONS, type LlamaOption, type OptionCategory } from "../shared/llamaOptions";

// ── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const FIT_COLORS: Record<FitStatus, string> = {
  GpuLikely: "#22c55e",
  PartialGpu: "#eab308",
  CpuOnly: "#3b82f6",
  Unlikely: "#ef4444",
};

const FIT_LABELS: Record<FitStatus, string> = {
  GpuLikely: "GPU Likely",
  PartialGpu: "Partial GPU",
  CpuOnly: "CPU Only",
  Unlikely: "Unlikely",
};

const CATEGORY_LABELS: Record<OptionCategory, string> = {
  model: "Model",
  server: "Server",
  sampling: "Sampling",
  performance: "Performance",
  advanced: "Advanced",
};

const CATEGORY_ORDER: OptionCategory[] = ["model", "performance", "server", "sampling", "advanced"];


function mergeSettings(base: LlamaSettings, override: Partial<LlamaSettings>): LlamaSettings {
  const merged = { ...base };
  for (const [k, v] of Object.entries(override)) {
    if (v !== undefined && v !== null && v !== "") {
      (merged as Record<string, unknown>)[k] = v;
    }
  }
  return merged;
}

// Convert a string hint value from a model card into a typed JS value.
function coerceHintValue(raw: string): unknown {
  if (raw === "true") return true;
  if (raw === "false") return false;
  if (raw === "null" || raw === "") return null;
  const asNum = Number(raw);
  if (!Number.isNaN(asNum) && raw.trim() !== "") return asNum;
  return raw;
}

// Extract HF repo/file hints from a modelsList rfilename like
// "Repo--Name/model.Q4.gguf". Returns nulls if the path doesn't look
// like an HF download.
function splitHfPath(rfilename: string): { hfRepo?: string; hfFile?: string } {
  const idx = rfilename.indexOf("/");
  if (idx <= 0) return {};
  return { hfRepo: rfilename.slice(0, idx), hfFile: rfilename.slice(idx + 1) };
}

function buildCommandArgv(modelPath: string, settings: LlamaSettings): string[] {
  const argv = ["llama-server", "-m", modelPath];

  for (const opt of LLAMA_OPTIONS) {
    if (!opt.settingKey) continue;
    const val = settings[opt.settingKey];
    if (val === undefined || val === null || val === "") continue;

    if (opt.valueType === "boolean") {
      if (val === true) {
        argv.push(opt.flag);
      } else if (val === false && opt.settingKey === "mmap") {
        argv.push("--no-mmap");
      }
    } else {
      argv.push(opt.flag, String(val));
    }
  }

  if (settings.extra_args?.length) {
    argv.push(...settings.extra_args);
  }

  return argv;
}

// ── OptionControl ──────────────────────────────────────────────────────────

function OptionControl({
  opt,
  value,
  onChange,
}: {
  opt: LlamaOption;
  value: unknown;
  onChange: (key: keyof LlamaSettings, val: unknown) => void;
}) {
  const id = `opt-${opt.flag.replace(/[^a-z0-9]/gi, "_")}`;
  const key = opt.settingKey;

  if (!key) return null;

  if (opt.valueType === "boolean") {
    return (
      <label className="run-option run-option-bool" title={opt.tooltip}>
        <input
          type="checkbox"
          id={id}
          checked={value === true}
          onChange={(e) => onChange(key, e.target.checked)}
        />
        <span className="run-option-flag">{opt.flag}</span>
      </label>
    );
  }

  if (opt.valueType === "number") {
    const step = opt.settingKey === "temp" || opt.settingKey === "top_p" || opt.settingKey === "min_p" || opt.settingKey === "repeat_penalty"
      ? 0.01
      : 1;
    return (
      <label className="run-option" title={opt.tooltip}>
        <span className="run-option-flag">{opt.flag}</span>
        <input
          type="number"
          id={id}
          className="run-option-input"
          value={value !== undefined && value !== null ? String(value) : ""}
          step={step}
          onChange={(e) => {
            const raw = e.target.value.trim();
            if (raw === "") {
              onChange(key, undefined);
            } else {
              const n = Number(raw);
              if (!Number.isNaN(n)) onChange(key, n);
            }
          }}
        />
      </label>
    );
  }

  return (
    <label className="run-option" title={opt.tooltip}>
      <span className="run-option-flag">{opt.flag}</span>
      <input
        type="text"
        id={id}
        className="run-option-input"
        value={value !== undefined && value !== null ? String(value) : ""}
        onChange={(e) => onChange(key, e.target.value || undefined)}
      />
    </label>
  );
}

// ── RunPage ────────────────────────────────────────────────────────────────
interface RunPageProps {
  config: AppConfig | null;
  initialModelPath: string | null;
  appliedHints: SettingHint[] | null;
  onAppliedHintsConsumed: () => void;
}

export default function RunPage({
  config,
  initialModelPath,
  appliedHints,
  onAppliedHintsConsumed,
}: RunPageProps) {
  const [models, setModels] = useState<GgufFileInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>(initialModelPath ?? "");
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>("__new");
  const [profileName, setProfileName] = useState<string>("");

  const [settings, setSettings] = useState<LlamaSettings>(
    { ...(config?.global_defaults ?? {}) },
  );
  const [serverState, setServerState] = useState<ServerStatus | null>(null);
  const [hardware, setHardware] = useState<HardwareInfo | null>(null);
  const [recommendation, setRecommendation] = useState<ModelRecommendation | null>(null);
  const [recLoading, setRecLoading] = useState(false);

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // ── Load models list ──────────────────────────────────────────────────
  const loadModels = useCallback(async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      const list = await modelsList();
      setModels(list);
    } catch (e: unknown) {
      setModelsError(e instanceof Error ? e.message : String(e));
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  // ── Load profiles for selected model ──────────────────────────────────
  const loadProfiles = useCallback(async () => {
    try {
      const all = await modelProfileList();
      const filtered = all.filter((p) => p.model_path === selectedModel);
      setProfiles(filtered);
      if (filtered.length > 0) {
        setSelectedProfileId(filtered[0].id);
        setProfileName(filtered[0].name);
        setSettings(mergeSettings({ ...(config?.global_defaults ?? {}) }, filtered[0].settings));
      } else {
        setSelectedProfileId("__new");
        setProfileName("Default");
        setSettings({ ...(config?.global_defaults ?? {}) });
      }
    } catch {
      setProfiles([]);
      setSelectedProfileId("__new");
    }
  }, [selectedModel, config?.global_defaults]);

  useEffect(() => {
    if (selectedModel) loadProfiles();
  }, [selectedModel, loadProfiles]);

  // ── Apply initialModelPath when it changes ────────────────────────────
  useEffect(() => {
    if (initialModelPath) setSelectedModel(initialModelPath);
  }, [initialModelPath]);

  // ── Apply suggested hints when HfModelPage hands them to us ──────────
  useEffect(() => {
    if (!appliedHints || appliedHints.length === 0) return;
    setSettings((prev) => {
      const next = { ...prev };
      for (const hint of appliedHints) {
        const v = coerceHintValue(hint.value);
        (next as Record<string, unknown>)[hint.key] = v;
      }
      return next;
    });
    setSaveMessage("Applied suggested settings from model card.");
    onAppliedHintsConsumed();
  }, [appliedHints, onAppliedHintsConsumed]);

  // ── Poll server status ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const st = await serverStatus();
        if (!cancelled) setServerState(st);
      } catch {
        // ignore
      }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // ── Load hardware info once ───────────────────────────────────────────
  useEffect(() => {
    hardwareScan()
      .then(setHardware)
      .catch(() => setHardware(null));
  }, []);

  // ── Command preview ───────────────────────────────────────────────────
  const commandPreview = useMemo(() => {
    if (!selectedModel) return "No model selected.";
    return buildCommandArgv(selectedModel, settings).join(" ");
  }, [selectedModel, settings]);

  // ── Selected model file size ──────────────────────────────────────────
  const selectedModelSize = useMemo<number | null>(() => {
    const m = models.find((f) => f.rfilename === selectedModel);
    return m?.size ?? null;
  }, [models, selectedModel]);

  // ── Handlers ──────────────────────────────────────────────────────────
  const updateSetting = useCallback((key: keyof LlamaSettings, val: unknown) => {
    setSettings((prev) => ({ ...prev, [key]: val }));
  }, []);

  const handleStart = useCallback(async () => {
    if (!selectedModel) return;
    setActionLoading(true);
    try {
      await serverStart(selectedModel, settings);
      const st = await serverStatus();
      setServerState(st);
    } catch (e: unknown) {
      setServerState({
        running: false,
        log_lines: [`Start failed: ${e instanceof Error ? e.message : String(e)}`],
      });
    } finally {
      setActionLoading(false);
    }
  }, [selectedModel, settings]);

  const handleStop = useCallback(async () => {
    setActionLoading(true);
    try {
      await serverStop();
      setServerState((prev) => (prev ? { ...prev, running: false } : prev));
    } finally {
      setActionLoading(false);
    }
  }, []);

  const handleRestart = useCallback(async () => {
    await handleStop();
    await handleStart();
  }, [handleStop, handleStart]);

  const handleCheckFit = useCallback(async () => {
    if (selectedModelSize === null || !hardware) return;
    setRecLoading(true);
    try {
      const rec = await modelRecommendation(selectedModelSize, hardware, settings);
      setRecommendation(rec);
    } catch {
      setRecommendation(null);
    } finally {
      setRecLoading(false);
    }
  }, [selectedModelSize, hardware, settings]);

  const handleApplyRecommendation = useCallback(() => {
    if (!recommendation) return;
    setSettings((prev) => ({
      ...prev,
      n_gpu_layers: recommendation.suggested_gpu_layers,
      ctx_size: recommendation.suggested_ctx_size,
      threads: recommendation.suggested_threads,
      batch_size: recommendation.suggested_batch_size,
    }));
    setRecommendation(null);
  }, [recommendation]);

  const handleSaveProfile = useCallback(async () => {
    if (!selectedModel) return;
    setSaveMessage(null);
    try {
      const { hfRepo, hfFile } = splitHfPath(selectedModel);
      const profile: ModelProfile = {
        id: selectedProfileId === "__new" ? crypto.randomUUID() : selectedProfileId,
        model_path: selectedModel,
        hf_repo: hfRepo,
        hf_file: hfFile,
        name: profileName || "Default",
        settings,
      };
      await modelProfileSave(profile);
      setSaveMessage("Profile saved.");
      await loadProfiles();
    } catch (e: unknown) {
      setSaveMessage(`Save failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [selectedModel, selectedProfileId, profileName, settings, loadProfiles]);

  // ── Grouped advanced options ──────────────────────────────────────────
  const advancedByCategory = useMemo(() => {
    const grouped: Partial<Record<OptionCategory, LlamaOption[]>> = {};
    for (const opt of LLAMA_OPTIONS) {
      // Skip the -m flag; it's set by the model picker, not manually
      if (opt.flag === "-m") continue;
      const cat = opt.category;
      (grouped[cat] ??= []).push(opt);
    }
    return grouped;
  }, []);

  // ── Quick settings options (subset) ───────────────────────────────────
  const quickSettingsKeys = useMemo(
    () =>
      new Set<keyof LlamaSettings>([
        "ctx_size",
        "n_gpu_layers",
        "threads",
        "batch_size",
        "parallel",
        "temp",
        "top_p",
      ]),
    [],
  );

  const quickOptions = useMemo(
    () => LLAMA_OPTIONS.filter((o) => o.settingKey && quickSettingsKeys.has(o.settingKey)),
    [quickSettingsKeys],
  );

  // ── Render ────────────────────────────────────────────────────────────

  const isRunning = serverState?.running ?? false;

  return (
    <div className="run-page">
      <h2>Run Model</h2>

      {/* ── Model picker ──────────────────────────────────────────────── */}
      <section className="run-section">
        <h3>Select Model</h3>
        {modelsLoading && <p className="run-muted">Loading models…</p>}
        {modelsError && <p className="run-error">{modelsError}</p>}
        {!modelsLoading && models.length === 0 && (
          <p className="run-muted">No GGUF models found. Download models or set the models directory in Setup.</p>
        )}
        {models.length > 0 && (
          <select
            className="run-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
          >
            <option value="">-- Choose a model --</option>
            {models.map((m) => (
              <option key={m.rfilename} value={m.rfilename}>
                {m.rfilename}
                {m.size != null ? ` (${formatBytes(m.size)})` : ""}
              </option>
            ))}
          </select>
        )}
      </section>

      {/* ── Profile selector ──────────────────────────────────────────── */}
      {selectedModel && (
        <section className="run-section">
          <h3>Profile</h3>
          <div className="run-profile-row">
            <select
              className="run-select run-profile-select"
              value={selectedProfileId}
              onChange={async (e) => {
                const id = e.target.value;
                setSelectedProfileId(id);
                if (id === "__new") {
                  setProfileName("Default");
                  setSettings({ ...(config?.global_defaults ?? {}) });
                } else {
                  const p = profiles.find((pr) => pr.id === id);
                  if (p) {
                    setProfileName(p.name);
                    setSettings(
                      mergeSettings({ ...(config?.global_defaults ?? {}) }, p.settings),
                    );
                  }
                }
              }}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              <option value="__new">+ New Profile</option>
            </select>
            <input
              type="text"
              className="run-input"
              placeholder="Profile name"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
            />
          </div>
        </section>
      )}

      {/* ── Quick settings ────────────────────────────────────────────── */}
      {selectedModel && (
        <section className="run-section">
          <h3>Quick Settings</h3>
          <div className="run-quick-grid">
            {quickOptions.map((opt) =>
              opt.settingKey ? (
                <OptionControl
                  key={opt.flag}
                  opt={opt}
                  value={settings[opt.settingKey]}
                  onChange={updateSetting}
                />
              ) : null,
            )}
          </div>
          {settings.n_gpu_layers !== undefined && settings.n_gpu_layers !== null && (
            <p className="run-helper">
              GPU layers: -1 = all, 0 = CPU only, 99 = auto-detect
            </p>
          )}
        </section>
      )}

      {/* ── Hardware fit ──────────────────────────────────────────────── */}
      {selectedModel && (
        <section className="run-section">
          <h3>Hardware Fit</h3>
          {!hardware ? (
            <p className="run-muted">Hardware info not available. Run a hardware scan in Setup.</p>
          ) : (
            <>
              <button
                className="run-btn run-btn-secondary"
                onClick={handleCheckFit}
                disabled={selectedModelSize === null || recLoading}
              >
                {recLoading ? "Checking…" : "Check Fit"}
              </button>

              {recommendation && (
                <div className="run-fit-result">
                  <div className="run-fit-badge-row">
                    <span
                      className="run-fit-badge"
                      style={{ backgroundColor: FIT_COLORS[recommendation.fit_status] }}
                    >
                      {FIT_LABELS[recommendation.fit_status]}
                    </span>
                    <span className="run-fit-confidence">
                      Confidence: {recommendation.confidence}
                    </span>
                  </div>
                  <div className="run-fit-estimates">
                    <span>Model: {formatBytes(recommendation.estimated_model_size_bytes)}</span>
                    <span>RAM needed: {formatBytes(recommendation.estimated_ram_required_bytes)}</span>
                    <span>VRAM needed: {formatBytes(recommendation.estimated_vram_required_bytes)}</span>
                  </div>
                  {recommendation.notes.length > 0 && (
                    <ul className="run-fit-notes">
                      {recommendation.notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  )}
                  <div className="run-fit-suggest">
                    <p>
                      Suggested: GPU layers={recommendation.suggested_gpu_layers}, ctx={recommendation.suggested_ctx_size},
                      threads={recommendation.suggested_threads}, batch={recommendation.suggested_batch_size}
                      {recommendation.use_fit_flag && ", --fit on"}
                    </p>
                    <button className="run-btn run-btn-secondary" onClick={handleApplyRecommendation}>
                      Apply Suggested Values
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      )}

      {/* ── Advanced accordion ────────────────────────────────────────── */}
      {selectedModel && (
        <section className="run-section">
          <button
            className="run-accordion-toggle"
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            {advancedOpen ? "▾" : "▸"} Advanced Options
          </button>
          {advancedOpen && (
            <div className="run-accordion-body">
              {CATEGORY_ORDER.map((cat) => {
                const opts = advancedByCategory[cat];
                if (!opts?.length) return null;
                return (
                  <div key={cat} className="run-adv-category">
                    <h4>{CATEGORY_LABELS[cat]}</h4>
                    <div className="run-adv-grid">
                      {opts.map((opt) =>
                        opt.settingKey ? (
                          <OptionControl
                            key={opt.flag}
                            opt={opt}
                            value={settings[opt.settingKey]}
                            onChange={updateSetting}
                          />
                        ) : (
                          <div key={opt.flag} className="run-option run-option-readonly" title={opt.tooltip}>
                            <span className="run-option-flag">{opt.flag}</span>
                            <span className="run-option-info">(set via other controls)</span>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* ── Command preview ───────────────────────────────────────────── */}
      {selectedModel && (
        <section className="run-section">
          <h3>Command Preview</h3>
          <textarea
            className="run-command-preview"
            readOnly
            rows={3}
            value={commandPreview}
          />
        </section>
      )}

      {/* ── Server controls ───────────────────────────────────────────── */}
      {selectedModel && (
        <section className="run-section run-controls">
          <div className="run-controls-row">
            {!isRunning ? (
              <button
                className="run-btn run-btn-primary"
                onClick={handleStart}
                disabled={actionLoading || !config?.llama_server_path}
              >
                {actionLoading ? "Starting…" : "Start Server"}
              </button>
            ) : (
              <>
                <button
                  className="run-btn run-btn-danger"
                  onClick={handleStop}
                  disabled={actionLoading}
                >
                  {actionLoading ? "Stopping…" : "Stop Server"}
                </button>
                <button
                  className="run-btn run-btn-secondary"
                  onClick={handleRestart}
                  disabled={actionLoading}
                >
                  Restart
                </button>
              </>
            )}
            <button
              className="run-btn run-btn-secondary"
              onClick={handleSaveProfile}
              disabled={!selectedModel}
            >
              Save Profile
            </button>
          </div>
          {saveMessage && <p className="run-save-msg">{saveMessage}</p>}

          {/* Status indicator */}
          <div className="run-status-bar">
            <span
              className="run-status-dot"
              style={{ backgroundColor: isRunning ? "#22c55e" : "#6b7280" }}
            />
            <span>
              {isRunning
                ? `Running (PID ${serverState?.pid ?? "?"})`
                : "Stopped"}
            </span>
            {isRunning && serverState?.health && (
              <span className="run-status-health">
                Health: {serverState.health}
              </span>
            )}
            {isRunning && config && (
              <span className="run-status-link">
                <a
                  href={`http://${settings.host ?? config.host}:${settings.port ?? config.port}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open UI →
                </a>
              </span>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
