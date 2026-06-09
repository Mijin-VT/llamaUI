import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Stack,
  Group,
  Text,
  Button,
  TextInput,
  NumberInput,
  PasswordInput,
  Badge,
  Alert,
  Table,
  Title,
  Grid,
  Code,
} from "@mantine/core";
import {
  IconFileSearch,
  IconFolder,
  IconCheck,
  IconX,
  IconDeviceFloppy,
  IconCpu,
  IconTrash,
} from "@tabler/icons-react";
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
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const val = bytes / Math.pow(1024, i);
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function tokenSourceLabel(source: AppConfig["hf_token_source"]): string {
  if (source === "none") return "No token";
  if (source === "env_var") return "Detected HF_TOKEN env var";
  if (typeof source === "object" && "saved" in source) return "Saved token";
  return "No token";
}

function tokenSourceBadgeColor(
  source: AppConfig["hf_token_source"],
): string {
  if (source === "env_var") return "green";
  if (typeof source === "object" && "saved" in source) return "blue";
  return "gray";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SetupPageProps {
  config: AppConfig | null;
  onConfigUpdate: (c: AppConfig) => void;
}

export default function SetupPage({
  config,
  onConfigUpdate,
}: SetupPageProps) {
  // Local form state — synced from config prop
  const [serverPath, setServerPath] = useState(
    config?.llama_server_path ?? "",
  );
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
    (
      nextTokenSource: AppConfig["hf_token_source"] = tokenSource,
    ): AppConfig => ({
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

    const nextTokenSource: AppConfig["hf_token_source"] = {
      saved: savedToken,
    };
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
    <Stack gap="lg">
      <Title order={2}>Setup</Title>

      {/* ---- Executable ---- */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h4">
            llama-server Executable
          </Title>
        </Card.Section>
        <Stack gap="sm" mt="sm">
          <Group align="flex-end" gap="sm" grow>
            <TextInput
              label="Path"
              value={serverPath}
              onChange={(e) => setServerPath(e.target.value)}
              placeholder="Path to llama-server binary"
            />
            <Button
              variant="default"
              loading={loading === "browse-server"}
              onClick={handleBrowseServer}
              leftSection={<IconFileSearch size={16} />}
            >
              Browse
            </Button>
          </Group>
          {!serverPath && (
            <Text size="sm" c="dimmed">
              Select the llama-server binary. This is required to launch
              models.
            </Text>
          )}
        </Stack>
      </Card>

      {/* ---- Models directory ---- */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h4">
            Model Download Directory
          </Title>
        </Card.Section>
        <Stack gap="sm" mt="sm">
          <Group align="flex-end" gap="sm" grow>
            <TextInput
              label="Directory"
              value={modelsDir}
              onChange={(e) => setModelsDir(e.target.value)}
              placeholder="Directory for downloaded GGUF files"
            />
            <Button
              variant="default"
              loading={loading === "browse-dir"}
              onClick={handleBrowseModelsDir}
              leftSection={<IconFolder size={16} />}
            >
              Browse
            </Button>
          </Group>
          {!modelsDir && (
            <Text size="sm" c="dimmed">
              Choose a folder where downloaded models will be stored.
            </Text>
          )}
        </Stack>
      </Card>

      {/* ---- HF Token ---- */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h4">
            Hugging Face Token
          </Title>
        </Card.Section>
        <Stack gap="sm" mt="sm">
          <Group align="center" gap="sm">
            <Text size="sm" fw={500}>
              Token source
            </Text>
            <Badge
              color={tokenSourceBadgeColor(tokenSource)}
              variant="light"
            >
              {tokenSourceLabel(tokenSource)}
            </Badge>
            {tokenSource !== "none" && (
              <Button
                variant="default"
                size="xs"
                loading={loading === "clear-token"}
                onClick={handleClearToken}
                leftSection={<IconTrash size={14} />}
              >
                Clear
              </Button>
            )}
          </Group>

          <Group align="flex-end" gap="sm" grow>
            <PasswordInput
              label="New token"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="hf_xxxxxxxx (optional)"
            />
            <Button
              loading={loading === "save-token"}
              disabled={!tokenInput.trim()}
              onClick={handleSaveToken}
              leftSection={<IconDeviceFloppy size={16} />}
            >
              Save
            </Button>
          </Group>

          <Group align="center" gap="sm">
            <Button
              variant="default"
              size="xs"
              loading={loading === "validate-token"}
              onClick={handleValidateToken}
              leftSection={<IconCheck size={14} />}
            >
              Validate Token
            </Button>
            {whoamiResult && (
              <Text size="sm" c="green">
                Authenticated as <Text span fw={700}>{whoamiResult}</Text>
              </Text>
            )}
            {whoamiError && (
              <Text size="sm" c="red">
                {whoamiError}
              </Text>
            )}
          </Group>

          <Text size="sm" c="dimmed">
            A token is optional but needed for gated models or higher rate
            limits. If the <Code>HF_TOKEN</Code> environment variable is set,
            it will be detected automatically.
          </Text>
        </Stack>
      </Card>

      {/* ---- Connection ---- */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h4">
            Connection Settings
          </Title>
        </Card.Section>
        <Stack gap="sm" mt="sm">
          <Group align="flex-start" gap="sm" grow>
            <TextInput
              label="Host"
              value={host}
              onChange={(e) => setHost(e.target.value)}
            />
            <NumberInput
              label="Port"
              min={1}
              max={65535}
              value={port}
              onChange={(val) => handlePortChange(String(val))}
            />
          </Group>
        </Stack>
      </Card>

      {/* ---- Hardware ---- */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h4">
            Hardware
          </Title>
        </Card.Section>
        <Stack gap="md" mt="sm">
          <Button
            variant="default"
            loading={loading === "scan-hardware"}
            onClick={handleScanHardware}
            leftSection={<IconCpu size={16} />}
          >
            Scan Hardware
          </Button>

          {hardware && (
            <>
              <Grid gutter="xs">
                <Grid.Col span={4}>
                  <Text size="sm" c="dimmed">
                    CPU
                  </Text>
                </Grid.Col>
                <Grid.Col span={8}>
                  <Text size="sm" ff="monospace">
                    {hardware.cpu_model}
                  </Text>
                </Grid.Col>

                <Grid.Col span={4}>
                  <Text size="sm" c="dimmed">
                    Cores / Threads
                  </Text>
                </Grid.Col>
                <Grid.Col span={8}>
                  <Text size="sm">
                    {hardware.cpu_cores} cores, {hardware.cpu_threads} threads
                  </Text>
                </Grid.Col>

                <Grid.Col span={4}>
                  <Text size="sm" c="dimmed">
                    RAM
                  </Text>
                </Grid.Col>
                <Grid.Col span={8}>
                  <Text size="sm">
                    {formatBytes(hardware.ram_total_bytes)} total,{" "}
                    {formatBytes(hardware.ram_available_bytes)} available
                  </Text>
                </Grid.Col>
              </Grid>

              {hardware.gpus.length > 0 && (
                <Stack gap="xs">
                  <Text fw={500} size="sm">
                    GPUs
                  </Text>
                  <Table highlightOnHover withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Name</Table.Th>
                        <Table.Th>VRAM Total</Table.Th>
                        <Table.Th>VRAM Free</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {hardware.gpus.map((gpu, i) => (
                        <Table.Tr key={i}>
                          <Table.Td>{gpu.name}</Table.Td>
                          <Table.Td>
                            {formatBytes(gpu.vram_total_bytes)}
                          </Table.Td>
                          <Table.Td>
                            {formatBytes(gpu.vram_free_bytes)}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Stack>
              )}

              {hardware.llama_devices.length > 0 && (
                <Stack gap="xs">
                  <Text fw={500} size="sm">
                    llama.cpp Devices
                  </Text>
                  <Table highlightOnHover withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>#</Table.Th>
                        <Table.Th>Name</Table.Th>
                        <Table.Th>VRAM Total</Table.Th>
                        <Table.Th>VRAM Free</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {hardware.llama_devices.map((dev) => (
                        <Table.Tr key={dev.index}>
                          <Table.Td>{dev.index}</Table.Td>
                          <Table.Td>{dev.name}</Table.Td>
                          <Table.Td>
                            {dev.vram_total_bytes != null
                              ? formatBytes(dev.vram_total_bytes)
                              : "—"}
                          </Table.Td>
                          <Table.Td>
                            {dev.vram_free_bytes != null
                              ? formatBytes(dev.vram_free_bytes)
                              : "—"}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Stack>
              )}
            </>
          )}
        </Stack>
      </Card>

      {/* ---- Save ---- */}
      {saveError && (
        <Alert color="red" variant="light" icon={<IconX size={16} />}>
          {saveError}
        </Alert>
      )}
      {saveSuccess && (
        <Alert color="green" variant="light" icon={<IconCheck size={16} />}>
          Configuration saved.
        </Alert>
      )}
      <Group justify="flex-end">
        <Button
          size="lg"
          loading={loading === "save"}
          onClick={handleSave}
          leftSection={<IconDeviceFloppy size={16} />}
        >
          Save Configuration
        </Button>
      </Group>
    </Stack>
  );
}
