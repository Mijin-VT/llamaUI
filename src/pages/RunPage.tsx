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
import {
  Card,
  Stack,
  Group,
  Grid,
  Text,
  Title,
  Button,
  Select,
  TextInput,
  NumberInput,
  Switch,
  Badge,
  Alert,
  Accordion,
  Tooltip,
  List,
  ThemeIcon,
  Textarea,
  Code,
  Box,
} from "@mantine/core";
import {
  IconX,
  IconCheck,
  IconRefresh,
  IconPlayerPlay,
  IconPlayerStop,
  IconDeviceFloppy,
  IconExternalLink,
  IconActivity,
} from "@tabler/icons-react";

// ── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const FIT_BADGE_COLORS: Record<FitStatus, string> = {
  GpuLikely: "green",
  PartialGpu: "yellow",
  CpuOnly: "blue",
  Unlikely: "red",
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

function coerceHintValue(raw: string): unknown {
  if (raw === "true") return true;
  if (raw === "false") return false;
  if (raw === "null" || raw === "") return null;
  const asNum = Number(raw);
  if (!Number.isNaN(asNum) && raw.trim() !== "") return asNum;
  return raw;
}

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
  const key = opt.settingKey;

  if (!key) return null;

  if (opt.valueType === "boolean") {
    return (
      <Tooltip label={opt.tooltip} withArrow position="top" disabled={!opt.tooltip}>
        <Switch
          label={opt.flag}
          checked={value === true}
          onChange={(e) => onChange(key, e.currentTarget.checked)}
          size="sm"
        />
      </Tooltip>
    );
  }

  if (opt.valueType === "number") {
    const step =
      opt.settingKey === "temp" ||
      opt.settingKey === "top_p" ||
      opt.settingKey === "min_p" ||
      opt.settingKey === "repeat_penalty"
        ? 0.01
        : 1;
    return (
      <Tooltip label={opt.tooltip} withArrow position="top" disabled={!opt.tooltip}>
        <NumberInput
          label={opt.flag}
          value={value !== undefined && value !== null ? Number(value) : undefined}
          step={step}
          onChange={(val) => onChange(key, val === "" ? undefined : val)}
          size="sm"
        />
      </Tooltip>
    );
  }

  return (
    <Tooltip label={opt.tooltip} withArrow position="top" disabled={!opt.tooltip}>
      <TextInput
        label={opt.flag}
        value={value !== undefined && value !== null ? String(value) : ""}
        onChange={(e) => onChange(key, e.currentTarget.value || undefined)}
        size="sm"
      />
    </Tooltip>
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

  const [settings, setSettings] = useState<LlamaSettings>({ ...(config?.global_defaults ?? {}) });
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

  const modelSelectData = useMemo(
    () =>
      models.map((m) => ({
        value: m.rfilename,
        label: `${m.rfilename}${m.size != null ? ` (${formatBytes(m.size)})` : ""}`,
      })),
    [models],
  );

  const profileSelectData = useMemo(
    () => [
      ...profiles.map((p) => ({ value: p.id, label: p.name })),
      { value: "__new", label: "+ New Profile" },
    ],
    [profiles],
  );

  return (
    <Stack gap="lg">
      <Title order={2}>Run Model</Title>

      {/* ── Model picker ──────────────────────────────────────────────── */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h5">
            Select Model
          </Title>
        </Card.Section>
        <Stack gap="sm" mt="sm">
          {modelsLoading && (
            <Text c="dimmed" size="sm">
              Loading models…
            </Text>
          )}
          {modelsError && (
            <Alert color="red" variant="light" icon={<IconX size={16} />}>
              {modelsError}
            </Alert>
          )}
          {!modelsLoading && models.length === 0 && (
            <Text c="dimmed" size="sm">
              No GGUF models found. Download models or set the models directory in Setup.
            </Text>
          )}
          {models.length > 0 && (
            <Select
              placeholder="-- Choose a model --"
              data={modelSelectData}
              value={selectedModel || null}
              onChange={(val) => setSelectedModel(val || "")}
            />
          )}
        </Stack>
      </Card>

      {/* ── Profile selector ──────────────────────────────────────────── */}
      {selectedModel && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">
              Profile
            </Title>
          </Card.Section>
          <Stack gap="sm" mt="sm">
            <Grid align="flex-end">
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Select
                  label="Profile"
                  data={profileSelectData}
                  value={selectedProfileId}
                  onChange={(val) => {
                    const id = val || "__new";
                    setSelectedProfileId(id);
                    if (id === "__new") {
                      setProfileName("Default");
                      setSettings({ ...(config?.global_defaults ?? {}) });
                    } else {
                      const p = profiles.find((pr) => pr.id === id);
                      if (p) {
                        setProfileName(p.name);
                        setSettings(mergeSettings({ ...(config?.global_defaults ?? {}) }, p.settings));
                      }
                    }
                  }}
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput
                  label="Profile Name"
                  placeholder="Profile name"
                  value={profileName}
                  onChange={(e) => setProfileName(e.currentTarget.value)}
                />
              </Grid.Col>
            </Grid>
          </Stack>
        </Card>
      )}

      {/* ── Quick settings ────────────────────────────────────────────── */}
      {selectedModel && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">
              Quick Settings
            </Title>
          </Card.Section>
          <Stack gap="sm" mt="sm">
            <Grid>
              {quickOptions.map((opt) =>
                opt.settingKey ? (
                  <Grid.Col key={opt.flag} span={{ base: 12, sm: 6, md: 4, lg: 3 }}>
                    <OptionControl
                      opt={opt}
                      value={settings[opt.settingKey]}
                      onChange={updateSetting}
                    />
                  </Grid.Col>
                ) : null,
              )}
            </Grid>
            {settings.n_gpu_layers !== undefined && settings.n_gpu_layers !== null && (
              <Text size="xs" c="dimmed">
                GPU layers: -1 = all, 0 = CPU only, 99 = auto-detect
              </Text>
            )}
          </Stack>
        </Card>
      )}

      {/* ── Hardware fit ──────────────────────────────────────────────── */}
      {selectedModel && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">
              Hardware Fit
            </Title>
          </Card.Section>
          <Stack gap="sm" mt="sm">
            {!hardware ? (
              <Text c="dimmed" size="sm">
                Hardware info not available. Run a hardware scan in Setup.
              </Text>
            ) : (
              <>
                <Button
                  variant="light"
                  onClick={handleCheckFit}
                  loading={recLoading}
                  disabled={selectedModelSize === null}
                  leftSection={<IconActivity size={16} />}
                >
                  Check Fit
                </Button>

                {recommendation && (
                  <Stack gap="xs">
                    <Group gap="sm">
                      <Badge color={FIT_BADGE_COLORS[recommendation.fit_status]} variant="light" size="lg">
                        {FIT_LABELS[recommendation.fit_status]}
                      </Badge>
                      <Text size="sm" c="dimmed">
                        Confidence: {recommendation.confidence}
                      </Text>
                    </Group>
                    <Group gap="md">
                      <Text size="sm">Model: {formatBytes(recommendation.estimated_model_size_bytes)}</Text>
                      <Text size="sm">RAM needed: {formatBytes(recommendation.estimated_ram_required_bytes)}</Text>
                      <Text size="sm">VRAM needed: {formatBytes(recommendation.estimated_vram_required_bytes)}</Text>
                    </Group>
                    {recommendation.notes.length > 0 && (
                      <List size="sm" spacing="xs" withPadding>
                        {recommendation.notes.map((n, i) => (
                          <List.Item key={i}>{n}</List.Item>
                        ))}
                      </List>
                    )}
                    <Stack gap="xs">
                      <Text size="sm">
                        Suggested: GPU layers={recommendation.suggested_gpu_layers}, ctx=
                        {recommendation.suggested_ctx_size}, threads={recommendation.suggested_threads}, batch=
                        {recommendation.suggested_batch_size}
                        {recommendation.use_fit_flag && ", --fit on"}
                      </Text>
                      <Button
                        variant="light"
                        onClick={handleApplyRecommendation}
                        leftSection={<IconCheck size={16} />}
                      >
                        Apply Suggested Values
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </>
            )}
          </Stack>
        </Card>
      )}

      {/* ── Advanced accordion ────────────────────────────────────────── */}
      {selectedModel && (
        <Accordion
          value={advancedOpen ? "advanced" : null}
          onChange={(val) => setAdvancedOpen(!!val)}
          variant="contained"
          radius="md"
        >
          <Accordion.Item value="advanced">
            <Accordion.Control>Advanced Options</Accordion.Control>
            <Accordion.Panel>
              <Stack gap="md">
                {CATEGORY_ORDER.map((cat) => {
                  const opts = advancedByCategory[cat];
                  if (!opts?.length) return null;
                  return (
                    <Stack key={cat} gap="xs">
                      <Title order={4} size="h6">
                        {CATEGORY_LABELS[cat]}
                      </Title>
                      <Grid>
                        {opts.map((opt) =>
                          opt.settingKey ? (
                            <Grid.Col key={opt.flag} span={{ base: 12, sm: 6, md: 4, lg: 3 }}>
                              <OptionControl
                                opt={opt}
                                value={settings[opt.settingKey]}
                                onChange={updateSetting}
                              />
                            </Grid.Col>
                          ) : (
                            <Grid.Col key={opt.flag} span={{ base: 12, sm: 6, md: 4, lg: 3 }}>
                              <Tooltip label={opt.tooltip} withArrow disabled={!opt.tooltip}>
                                <Box>
                                  <Code>{opt.flag}</Code>{" "}
                                  <Text span c="dimmed" size="sm">
                                    (set via other controls)
                                  </Text>
                                </Box>
                              </Tooltip>
                            </Grid.Col>
                          ),
                        )}
                      </Grid>
                    </Stack>
                  );
                })}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      )}

      {/* ── Command preview ───────────────────────────────────────────── */}
      {selectedModel && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">
              Command Preview
            </Title>
          </Card.Section>
          <Box mt="sm">
            <Textarea readOnly rows={3} value={commandPreview} />
          </Box>
        </Card>
      )}

      {/* ── Server controls ───────────────────────────────────────────── */}
      {selectedModel && (
        <Card withBorder>
          <Stack gap="sm">
            <Group gap="sm" wrap="nowrap">
              {!isRunning ? (
                <Button
                  onClick={handleStart}
                  loading={actionLoading}
                  disabled={!config?.llama_server_path}
                  leftSection={<IconPlayerPlay size={16} />}
                >
                  Start Server
                </Button>
              ) : (
                <>
                  <Button
                    color="red"
                    onClick={handleStop}
                    loading={actionLoading}
                    leftSection={<IconPlayerStop size={16} />}
                  >
                    Stop Server
                  </Button>
                  <Button
                    variant="light"
                    onClick={handleRestart}
                    disabled={actionLoading}
                    leftSection={<IconRefresh size={16} />}
                  >
                    Restart
                  </Button>
                </>
              )}
              <Button
                variant="light"
                onClick={handleSaveProfile}
                disabled={!selectedModel}
                leftSection={<IconDeviceFloppy size={16} />}
              >
                Save Profile
              </Button>
            </Group>

            {saveMessage && (
              <Alert
                color={saveMessage.includes("failed") ? "red" : "green"}
                variant="light"
                icon={saveMessage.includes("failed") ? <IconX size={16} /> : <IconCheck size={16} />}
              >
                {saveMessage}
              </Alert>
            )}

            <Group gap="sm" wrap="nowrap">
              <ThemeIcon color={isRunning ? "green" : "gray"} size={12} radius="xl" />
              <Text size="sm">
                {isRunning ? `Running (PID ${serverState?.pid ?? "?"})` : "Stopped"}
              </Text>
              {isRunning && serverState?.health && (
                <Badge color="blue" variant="light" size="sm">
                  Health: {serverState.health}
                </Badge>
              )}
              {isRunning && config && (
                <Button
                  component="a"
                  href={`http://${settings.host ?? config.host}:${settings.port ?? config.port}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="subtle"
                  size="xs"
                  rightSection={<IconExternalLink size={14} />}
                >
                  Open UI
                </Button>
              )}
            </Group>
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
