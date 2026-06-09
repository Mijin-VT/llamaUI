import { useState, useEffect, useCallback } from "react";
import { AppShell, Tabs, Text, Group, Box } from "@mantine/core";
import {
  IconSettings,
  IconDownload,
  IconFileDescription,
  IconPlayerPlay,
  IconActivity,
  IconStethoscope,
} from "@tabler/icons-react";
import { getConfig } from "./shared/tauriApi";
import type { AppConfig, SettingHint } from "./shared/types";
import SetupPage from "./pages/SetupPage";
import DownloadPage from "./pages/DownloadPage";
import HfModelPage from "./pages/HfModelPage";
import RunPage from "./pages/RunPage";
import StatusPage from "./pages/StatusPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";

const iconMap: Record<string, React.ReactNode> = {
  setup: <IconSettings size={16} />,
  download: <IconDownload size={16} />,
  "hf-model": <IconFileDescription size={16} />,
  run: <IconPlayerPlay size={16} />,
  status: <IconActivity size={16} />,
  diagnostics: <IconStethoscope size={16} />,
};

type Page = "setup" | "download" | "hf-model" | "run" | "status" | "diagnostics";

interface AppSharedState {
  config: AppConfig | null;
  selectedHfRepo: string | null;
  selectedModelPath: string | null;
  appliedHints: SettingHint[] | null;
}

export default function App() {
  const [page, setPage] = useState<Page>("setup");
  const [shared, setShared] = useState<AppSharedState>({
    config: null,
    selectedHfRepo: null,
    selectedModelPath: null,
    appliedHints: null,
  });

  useEffect(() => {
    getConfig()
      .then((config) => setShared((s) => ({ ...s, config })))
      .catch(console.error);
  }, []);

  const updateConfig = useCallback((config: AppConfig) => {
    setShared((s) => ({ ...s, config }));
  }, []);

  const selectHfRepo = useCallback((repoId: string) => {
    setShared((s) => ({ ...s, selectedHfRepo: repoId }));
    setPage("hf-model");
  }, []);

  const selectModel = useCallback((modelPath: string) => {
    setShared((s) => ({ ...s, selectedModelPath: modelPath }));
    setPage("run");
  }, []);

  const applyHints = useCallback((hints: SettingHint[]) => {
    setShared((s) => ({ ...s, appliedHints: hints }));
  }, []);

  const clearAppliedHints = useCallback(() => {
    setShared((s) => ({ ...s, appliedHints: null }));
  }, []);

  const goToRun = useCallback(() => {
    setPage("run");
  }, []);

  const tabs: { id: Page; label: string }[] = [
    { id: "setup", label: "Setup" },
    { id: "download", label: "Download" },
    { id: "hf-model", label: "Model Detail" },
    { id: "run", label: "Run" },
    { id: "status", label: "Status" },
    { id: "diagnostics", label: "Diagnostics" },
  ];

  return (
    <AppShell
      header={{ height: 48 }}
      styles={{
        header: {
          backgroundColor: "#161922",
          borderBottom: "1px solid #2a2e3b",
        },
        main: {
          backgroundColor: "#0f1117",
        },
      }}
    >
      <AppShell.Header>
        <Group h="100%" px="md" gap="xs" wrap="nowrap">
          <Text fw={700} size="lg" c="blue.4">
            llamaUI
          </Text>
          <Box style={{ flex: 1 }}>
            <Tabs
              value={page}
              onChange={(v) => setPage(v as Page)}
              variant="pills"
              radius="sm"
            >
              <Tabs.List style={{ background: "transparent", gap: 4 }}>
                {tabs.map((t) => (
                  <Tabs.Tab
                    key={t.id}
                    value={t.id}
                    leftSection={iconMap[t.id]}
                    styles={{
                      tab: {
                        color: page === t.id ? "#e2e4e9" : "#9aa0b2",
                        backgroundColor:
                          page === t.id
                            ? "rgba(14, 165, 233, 0.15)"
                            : "transparent",
                        fontWeight: page === t.id ? 600 : 400,
                        fontSize: 13,
                        padding: "6px 12px",
                        whiteSpace: "nowrap",
                      },
                    }}
                  >
                    {t.label}
                  </Tabs.Tab>
                ))}
              </Tabs.List>
            </Tabs>
          </Box>
        </Group>
      </AppShell.Header>

      <AppShell.Main p="md">
        {page === "setup" && (
          <SetupPage config={shared.config} onConfigUpdate={updateConfig} />
        )}
        {page === "download" && (
          <DownloadPage
            config={shared.config}
            onSelectRepo={selectHfRepo}
            onSelectModel={selectModel}
          />
        )}
        {page === "hf-model" && (
          <HfModelPage
            repoId={shared.selectedHfRepo}
            config={shared.config}
            onApplyHints={applyHints}
            onGoToRun={goToRun}
          />
        )}
        {page === "run" && (
          <RunPage
            config={shared.config}
            initialModelPath={shared.selectedModelPath}
            appliedHints={shared.appliedHints}
            onAppliedHintsConsumed={clearAppliedHints}
          />
        )}
        {page === "status" && <StatusPage config={shared.config} />}
        {page === "diagnostics" && <DiagnosticsPage />}
      </AppShell.Main>
    </AppShell>
  );
}
