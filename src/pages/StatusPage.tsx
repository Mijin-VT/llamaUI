import { useState, useEffect, useCallback, useRef } from "react";
import type { AppConfig, ServerStatus as ServerStatusType } from "../shared/types";
import {
  serverStop,
  serverStatus,
  onServerLog,
  onServerStarted,
} from "../shared/tauriApi";
import {
  Card,
  Stack,
  Group,
  Text,
  Button,
  Title,
  Code,
  Alert,
  Badge,
  Anchor,
  CopyButton,
  ScrollArea,
  Box,
  Table,
} from "@mantine/core";
import {
  IconActivity,
  IconPlayerStop,
  IconRefresh,
  IconTrash,
  IconLink,
  IconCopy,
  IconTerminal,
  IconX,
} from "@tabler/icons-react";

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
  const logViewportRef = useRef<HTMLDivElement>(null);
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
    const el = logViewportRef.current;
    if (!el || !autoScrollRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [logs]);

  // --- Initial status fetch ---
  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  // --- Detect manual scroll to pause/resume auto-scroll ---
  const handleLogScrollPosition = useCallback(
    ({ y }: { x: number; y: number }) => {
      const el = logViewportRef.current;
      if (!el) return;
      const atBottom = el.scrollHeight - y - el.clientHeight < 20;
      autoScrollRef.current = atBottom;
    },
    []
  );

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

  // --- Health display ---
  let healthLabel: string;
  let healthColor: string;
  if (!running) {
    healthLabel = "Stopped";
    healthColor = "gray";
  } else if (health === "ok") {
    healthLabel = "Healthy";
    healthColor = "green";
  } else if (health === "loading") {
    healthLabel = "Loading model…";
    healthColor = "yellow";
  } else if (health === "error") {
    healthLabel = "Error";
    healthColor = "red";
  } else {
    // running but health is undefined/null — unreachable or not yet polled
    healthLabel = "Unreachable";
    healthColor = "yellow";
  }

  return (
    <Stack gap="md">
      <Group gap="xs" align="center">
        <IconActivity size={24} />
        <Title order={2}>Server Status</Title>
      </Group>

      {error && (
        <Alert color="red" variant="light" icon={<IconX size={16} />}>
          {error}
        </Alert>
      )}

      {/* --- Status overview --- */}
      <Card withBorder>
        <Table highlightOnHover withTableBorder={false} layout="fixed">
          <Table.Tbody>
            <Table.Tr>
              <Table.Th w="120">State</Table.Th>
              <Table.Td>
                <Badge color={running ? "green" : "gray"} variant="light">
                  {running ? "Running" : "Stopped"}
                </Badge>
              </Table.Td>
            </Table.Tr>

            <Table.Tr>
              <Table.Th>PID</Table.Th>
              <Table.Td>
                <Code>{pid != null ? pid : "—"}</Code>
              </Table.Td>
            </Table.Tr>

            <Table.Tr>
              <Table.Th>Started</Table.Th>
              <Table.Td>
                <Text>{startedAt ? new Date(startedAt).toLocaleString() : "—"}</Text>
              </Table.Td>
            </Table.Tr>

            <Table.Tr>
              <Table.Th>Health</Table.Th>
              <Table.Td>
                <Badge color={healthColor} variant="light">
                  {healthLabel}
                </Badge>
              </Table.Td>
            </Table.Tr>

            {running && (
              <Table.Tr>
                <Table.Th>Web UI</Table.Th>
                <Table.Td>
                  <Group gap="xs" align="center" wrap="nowrap">
                    <IconLink size={14} />
                    <Anchor
                      href={serverUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      size="sm"
                    >
                      {serverUrl}
                    </Anchor>
                    <CopyButton value={serverUrl}>
                      {({ copied, copy }) => (
                        <Button
                          variant="subtle"
                          size="compact-xs"
                          leftSection={<IconCopy size={14} />}
                          onClick={copy}
                          color={copied ? "teal" : "blue"}
                        >
                          {copied ? "Copied" : "Copy"}
                        </Button>
                      )}
                    </CopyButton>
                  </Group>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Card>

      {/* --- Controls (no Start: the user starts the server from the Run page) --- */}
      <Group gap="sm" align="center" wrap="wrap">
        {running && (
          <Button
            color="red"
            leftSection={<IconPlayerStop size={16} />}
            onClick={handleStop}
            loading={loading}
          >
            Stop Server
          </Button>
        )}
        <Button
          variant="default"
          leftSection={<IconRefresh size={16} />}
          onClick={refreshStatus}
          loading={loading}
        >
          Refresh
        </Button>
        {!running && (
          <Text size="sm" c="dimmed">
            To start a model, go to the <Text span fw={700}>Run</Text> page and
            pick a model.
          </Text>
        )}
      </Group>

      {/* --- Generated command --- */}
      {command && (
        <Card withBorder>
          <Card.Section withBorder inheritPadding py="xs">
            <Title order={3} size="h5">
              Generated Command
            </Title>
          </Card.Section>
          <Stack gap="sm" mt="sm">
            <Code block>{command}</Code>
            <Group justify="flex-end">
              <CopyButton value={command}>
                {({ copied, copy }) => (
                  <Button
                    variant="subtle"
                    size="compact-sm"
                    leftSection={<IconCopy size={16} />}
                    onClick={copy}
                    color={copied ? "teal" : "blue"}
                  >
                    {copied ? "Copied" : "Copy"}
                  </Button>
                )}
              </CopyButton>
            </Group>
          </Stack>
        </Card>
      )}

      {/* --- Logs --- */}
      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Group justify="space-between" align="center">
            <Group gap="xs" align="center">
              <IconTerminal size={16} />
              <Title order={3} size="h5">
                Logs
              </Title>
            </Group>
            <Button
              variant="subtle"
              size="compact-sm"
              leftSection={<IconTrash size={16} />}
              onClick={handleClearLogs}
            >
              Clear
            </Button>
          </Group>
        </Card.Section>
        <Box mt="sm">
          <ScrollArea
            h={300}
            viewportRef={logViewportRef}
            onScrollPositionChange={handleLogScrollPosition}
          >
            <Code block>
              {logs.length === 0
                ? "(no logs yet)"
                : logs.join("\n")}
            </Code>
          </ScrollArea>
        </Box>
      </Card>
    </Stack>
  );
}
