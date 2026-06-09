import { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  Stack,
  Group,
  Grid,
  Text,
  Button,
  TextInput,
  Badge,
  Alert,
  Progress,
  Title,
  Box,
} from "@mantine/core";
import classes from "./DownloadPage.module.css";
import {
  IconSearch,
  IconCaretDown,
  IconCaretRight,
  IconDownload,
  IconCheck,
  IconPlayerPlay,
  IconX,
  IconRefresh,
  IconAlertTriangle,
  IconHeart,
} from "@tabler/icons-react";
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
      <Box key={file.rfilename} py="xs">
        <Group justify="space-between" wrap="nowrap" gap="sm">
          <Group gap="sm" wrap="nowrap">
            <Text size="sm" fw={500}>
              {file.rfilename}
            </Text>
            {file.size != null && (
              <Text size="xs" c="dimmed">
                {formatBytes(file.size)}
              </Text>
            )}
          </Group>

          <Group gap="xs" wrap="nowrap">
            {isDone && (
              <>
                <Text size="sm" c="green">
                  <IconCheck size={16} />{" "}
                  Downloaded
                </Text>
                {localPathFor(file.rfilename) && (
                  <Button
                    size="xs"
                    leftSection={<IconPlayerPlay size={14} />}
                    onClick={() =>
                      onSelectModel(localPathFor(file.rfilename)!)
                    }
                  >
                    Run this model
                  </Button>
                )}
              </>
            )}
            {isDownloading && (
              <Button
                size="xs"
                color="red"
                onClick={() => cancelDownload(repoId, file.rfilename)}
              >
                Cancel
              </Button>
            )}
            {!isDone && !isDownloading && !hasError && (
              <Button
                size="xs"
                leftSection={<IconDownload size={14} />}
                disabled={!config?.models_dir}
                title={
                  config?.models_dir
                    ? "Download to models directory"
                    : "Set a models directory in Setup first"
                }
                onClick={() => startDownload(repoId, file.rfilename)}
              >
                Download
              </Button>
            )}
            {hasError && (
              <Button
                size="xs"
                leftSection={<IconRefresh size={14} />}
                disabled={!config?.models_dir}
                onClick={() => startDownload(repoId, file.rfilename)}
              >
                Retry
              </Button>
            )}
          </Group>
        </Group>

        {/* Progress bar */}
        {isDownloading && (
          <Box mt="xs">
            <Progress
              value={pct ?? 0}
              size="sm"
              radius="sm"
              striped
              animated
            />
            <Text size="xs" c="dimmed" mt={4}>
              {formatBytes(prog!.bytes_downloaded)}
              {prog!.bytes_total ? ` / ${formatBytes(prog!.bytes_total)}` : ""}
              {pct != null ? ` (${pct}%)` : ""}
            </Text>
          </Box>
        )}

        {/* Error */}
        {hasError && (
          <Text size="sm" c="red" mt="xs">
            {prog!.error}
          </Text>
        )}
      </Box>
    );
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const noModelsDir = !config?.models_dir;

  return (
    <Stack gap="md">
      <Title order={2}>Download Models</Title>

      {noModelsDir && (
        <Alert
          color="yellow"
          variant="light"
          icon={<IconAlertTriangle size={16} />}
        >
          Set a models directory in Setup before downloading.
        </Alert>
      )}

      {/* Search */}
      <Grid align="flex-end" gutter="sm">
        <Grid.Col span="auto">
          <TextInput
            label="Search HuggingFace"
            placeholder="Search HuggingFace for GGUF models…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={searching}
          />
        </Grid.Col>
        <Grid.Col span="content">
          <Button
            leftSection={<IconSearch size={16} />}
            onClick={doSearch}
            loading={searching}
            disabled={query.trim().length === 0}
          >
            Search HuggingFace
          </Button>
        </Grid.Col>
      </Grid>

      {/* Errors */}
      {searchError && (
        <Alert color="red" variant="light" icon={<IconX size={16} />}>
          {searchError}
        </Alert>
      )}

      {/* Results */}
      {results.length === 0 &&
        !searching &&
        !searchError &&
        query.trim().length > 0 && (
          <Text c="dimmed">No results found.</Text>
        )}

      <Stack gap="md">
        {results.map((repo) => {
          const isExpanded = expanded.has(repo.id);
          return (
            <Card key={repo.id} withBorder>
              <Card.Section
                withBorder
                inheritPadding
                py="sm"
                className={classes.clickable}
                onClick={() => toggleExpand(repo.id)}
              >
                <Stack gap="xs">
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap="xs" wrap="nowrap">
                      <Button
                        variant="subtle"
                        size="compact-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRepo(repo.id);
                        }}
                        title="View model details"
                      >
                        <Text fw={600}>{repo.id}</Text>
                      </Button>
                      <Text c="dimmed">
                        {isExpanded ? (
                          <IconCaretDown size={16} />
                        ) : (
                          <IconCaretRight size={16} />
                        )}
                      </Text>
                    </Group>

                    <Group gap="sm" wrap="nowrap">
                      <Text size="sm" c="dimmed" title="Downloads">
                        <IconDownload size={14} />{" "}
                        {repo.downloads.toLocaleString()}
                      </Text>
                      <Text size="sm" c="dimmed" title="Likes">
                        <IconHeart size={14} /> {repo.likes.toLocaleString()}
                      </Text>
                      {repo.gated && (
                        <Badge color="yellow" variant="light">
                          Gated
                        </Badge>
                      )}
                      {repo.private && (
                        <Badge color="red" variant="light">
                          Private
                        </Badge>
                      )}
                    </Group>
                  </Group>

                  <Group gap="xs" wrap="wrap">
                    {repo.tags.slice(0, 8).map((t) => (
                      <Badge key={t} variant="default" size="sm">
                        {t}
                      </Badge>
                    ))}
                    {repo.tags.length > 8 && (
                      <Badge variant="default" size="sm" color="gray">
                        +{repo.tags.length - 8}
                      </Badge>
                    )}
                  </Group>

                  <Text size="sm" c="dimmed">
                    {repo.gguf_files.length} GGUF file
                    {repo.gguf_files.length !== 1 ? "s" : ""}
                  </Text>
                </Stack>
              </Card.Section>

              {isExpanded && (
                <Card.Section inheritPadding py="sm">
                  {repo.gguf_files.length === 0 && (
                    <Text c="dimmed" size="sm">
                      No GGUF files listed.
                    </Text>
                  )}
                  <Stack gap={0}>
                    {repo.gguf_files.map((file) => renderFile(repo.id, file))}
                  </Stack>
                </Card.Section>
              )}
            </Card>
          );
        })}
      </Stack>
    </Stack>
  );
}
