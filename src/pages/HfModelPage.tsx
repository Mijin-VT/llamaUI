import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Accordion,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  List,
  Progress,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  IconCheck,
  IconDownload,
  IconSettings,
  IconX,
} from "@tabler/icons-react";
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
      <Stack gap="md">
        <Title order={2}>Hugging Face Model Detail</Title>
        <Text c="dimmed">Select a model from the Download page to view its details.</Text>
      </Stack>
    );
  }

  // ── Loading state ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <Stack gap="md">
        <Title order={2}>{repoId}</Title>
        <Text>Loading model details…</Text>
      </Stack>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────
  if (error && !card) {
    return (
      <Stack gap="md">
        <Title order={2}>{repoId}</Title>
        <Alert color="red" variant="light" icon={<IconX size={16} />}>
          Failed to load model details: {error}
        </Alert>
      </Stack>
    );
  }

  const cardData = card?.card_data;
  const hints = card?.suggested_settings ?? [];

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <Stack gap="md">
      <Title order={2}>{repoId}</Title>

      {/* ── Metadata panel ─────────────────────────────────────────────── */}
      <Card withBorder>
        <Accordion defaultValue="info">
          <Accordion.Item value="info">
            <Accordion.Control>
              <Title order={3} size="h5">Model Information</Title>
            </Accordion.Control>
            <Accordion.Panel>
              <List size="sm" withPadding={false} listStyleType="none">
                {cardData?.pipeline_tag && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">Pipeline</Text>
                      <Text size="sm">{cardData.pipeline_tag}</Text>
                    </Group>
                  </List.Item>
                )}
                {cardData?.base_model && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">Base Model</Text>
                      <Text size="sm">{cardData.base_model}</Text>
                    </Group>
                  </List.Item>
                )}
                {cardData?.license && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">License</Text>
                      <Text size="sm">{cardData.license}</Text>
                    </Group>
                  </List.Item>
                )}
                {cardData?.model_type && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">Model Type</Text>
                      <Text size="sm">{cardData.model_type}</Text>
                    </Group>
                  </List.Item>
                )}
                {cardData?.library_name && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">Library</Text>
                      <Text size="sm">{cardData.library_name}</Text>
                    </Group>
                  </List.Item>
                )}
                {cardData?.language && cardData.language.length > 0 && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">Languages</Text>
                      <Text size="sm">{cardData.language.join(", ")}</Text>
                    </Group>
                  </List.Item>
                )}
                {(cardData?.tags?.length ?? 0) > 0 && (
                  <List.Item>
                    <Group justify="space-between" align="flex-start">
                      <Text fw={500} size="sm">Tags</Text>
                      <Group gap="xs" wrap="wrap">
                        {cardData!.tags!.map((t) => (
                          <Badge key={t} variant="light" size="sm">
                            {t}
                          </Badge>
                        ))}
                      </Group>
                    </Group>
                  </List.Item>
                )}
                {card?.repo_id && (
                  <List.Item>
                    <Group justify="space-between">
                      <Text fw={500} size="sm">Repository</Text>
                      <Anchor
                        href={`https://huggingface.co/${card.repo_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        size="sm"
                      >
                        {card.repo_id}
                      </Anchor>
                    </Group>
                  </List.Item>
                )}
              </List>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Card>

      {/* ── GGUF files table ───────────────────────────────────────────── */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h5">GGUF Files</Title>
        </Card.Section>
        <Stack gap="sm" mt="sm">
          {regularGguf.length === 0 && mmprojFiles.length === 0 ? (
            <Text c="dimmed">No GGUF files found in this repository.</Text>
          ) : (
            <ScrollArea>
              <Table highlightOnHover withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>File</Table.Th>
                    <Table.Th>Type</Table.Th>
                    <Table.Th>Size</Table.Th>
                    <Table.Th>Action</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
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
                </Table.Tbody>
              </Table>
            </ScrollArea>
          )}
        </Stack>
      </Card>

      {/* ── Setting hints ──────────────────────────────────────────────── */}
      {hints.length > 0 && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">Suggested Settings</Title>
          </Card.Section>
          <Stack gap="sm" mt="sm">
            <Text c="dimmed" size="sm">
              These settings were detected from the model card and may improve
              performance or are required for correct behaviour.
            </Text>
            <Table highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Setting</Table.Th>
                  <Table.Th>Value</Table.Th>
                  <Table.Th>Source</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {hints.map((h, i) => (
                  <Table.Tr key={`${h.key}-${i}`}>
                    <Table.Td>
                      <Text ff="monospace" size="sm">{h.key}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text ff="monospace" size="sm">{h.value}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" size="sm">{h.source}</Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Button
              leftSection={<IconSettings size={16} />}
              loading={applyingSettings}
              onClick={handleApplySettings}
            >
              Apply these settings
            </Button>
          </Stack>
        </Card>
      )}

      {/* ── Model card README ──────────────────────────────────────────── */}
      {card?.readme && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">Model Card</Title>
          </Card.Section>
          <ScrollArea h={400} mt="sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {card.readme}
            </ReactMarkdown>
          </ScrollArea>
        </Card>
      )}

      {/* ── No readme fallback ─────────────────────────────────────────── */}
      {!card?.readme && !error && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">Model Card</Title>
          </Card.Section>
          <Text c="dimmed" mt="sm">
            No README/model card available for this repository.
          </Text>
        </Card>
      )}

      {/* ── Non-blocking error banner ──────────────────────────────────── */}
      {error && card && (
        <Alert color="red" variant="light" icon={<IconX size={16} />} mt="md">
          Some data could not be loaded: {error}
        </Alert>
      )}
    </Stack>
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
    <Table.Tr>
      <Table.Td title={name}>
        <Text ff="monospace" size="sm">{name}</Text>
      </Table.Td>
      <Table.Td>
        <Badge
          color={typeLabel === "Multimodal projector" ? "violet" : "blue"}
          variant="light"
          size="sm"
        >
          {typeLabel}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{formatBytes(sibling.size)}</Text>
      </Table.Td>
      <Table.Td>
        {!done && !active && !failed && (
          <Button
            size="xs"
            leftSection={<IconDownload size={14} />}
            disabled={!modelsDir}
            title={
              modelsDir
                ? `Download to ${modelsDir}`
                : "Set a models directory in Setup first"
            }
            onClick={() => onDownload(name)}
          >
            Download
          </Button>
        )}
        {active && (
          <Group grow align="center" wrap="nowrap">
            <Progress value={progressPct} size="sm" />
            <Group gap="sm" align="center" wrap="nowrap">
              <Text size="xs">
                {formatBytes(dlState!.bytesDownloaded)} / {formatBytes(dlState!.bytesTotal)} ({progressPct}%)
              </Text>
              <Button size="xs" color="red" variant="light" onClick={() => onCancel(name)}>
                Cancel
              </Button>
            </Group>
          </Group>
        )}
        {done && !active && (
          <Group gap={4} align="center">
            <IconCheck size={16} color="var(--mantine-color-green-6)" />
            <Text c="green" size="sm">
              Downloaded{isLocal && !dlState?.done ? " (local)" : ""}
            </Text>
          </Group>
        )}
        {failed && (
          <Group gap={4} align="center">
            <IconX size={16} color="var(--mantine-color-red-6)" />
            <Text c="red" size="sm" title={dlState!.error}>
              Failed
            </Text>
          </Group>
        )}
      </Table.Td>
    </Table.Tr>
  );
}
