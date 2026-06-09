import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Code,
  Group,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconRefresh, IconX } from "@tabler/icons-react";
import { frameworkDiagnostics } from "../shared/tauriApi";
import type { FrameworkDiagnostics } from "../shared/types";

function valueText(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (value === undefined || value === null || value === "") return "—";
  return String(value);
}

export default function DiagnosticsPage() {
  const [diagnostics, setDiagnostics] = useState<FrameworkDiagnostics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDiagnostics(await frameworkDiagnostics());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows: Array<[string, unknown]> = diagnostics
    ? [
        ["Framework", diagnostics.framework],
        ["Dialog backend", diagnostics.dialog_backend],
        ["XDG session", diagnostics.xdg_session_type],
        ["Current desktop", diagnostics.xdg_current_desktop],
        ["Desktop session", diagnostics.desktop_session],
        ["GDK backend", diagnostics.gdk_backend],
        ["Wayland display", diagnostics.wayland_display],
        ["X11 display", diagnostics.display],
        ["Qt platform", diagnostics.qt_qpa_platform],
        ["Portal descriptors", diagnostics.portal_descriptors],
        ["Active portal", diagnostics.active_portal_name],
        ["Portal DBus reachable", diagnostics.portal_dbus_reachable],
        ["GPU vendor", diagnostics.gpu_vendor],
        ["GPU driver", diagnostics.gpu_driver_version],
        ["NVIDIA driver", diagnostics.nvidia_driver_present],
        ["Explicit sync disabled", diagnostics.explicit_sync_disabled],
        ["Workaround applied", diagnostics.workaround_applied],
        ["Workaround set by app", diagnostics.workaround_inputs.set_by_us],
        ["Workaround env already set", diagnostics.workaround_inputs.env_already_set],
      ]
    : [];

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <Title order={2}>Diagnostics</Title>
        <Button
          loading={loading}
          variant="light"
          leftSection={<IconRefresh size={16} />}
          onClick={load}
        >
          Refresh
        </Button>
      </Group>

      <Card withBorder>
        <Card.Section withBorder inheritPadding py="xs">
          <Title order={3} size="h3">
            Framework viability
          </Title>
        </Card.Section>

        <Stack gap="sm" mt="sm">
          <Text c="dimmed" size="sm">
            Phase 1 gate: prove native KDE Wayland + NVIDIA operation before
            committing to Tauri.
          </Text>

          {error && (
            <Alert color="red" variant="light" icon={<IconX size={16} />}>
              {error}
            </Alert>
          )}

          <Table highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Property</Table.Th>
                <Table.Th>Value</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map(([label, value]) => (
                <Table.Tr key={label}>
                  <Table.Td>{label}</Table.Td>
                  <Table.Td>
                    <Code>{valueText(value)}</Code>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Stack>
      </Card>
    </Stack>
  );
}
