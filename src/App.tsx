import { useState, useEffect, useCallback } from "react";
import { getConfig } from "./shared/tauriApi";
import type { AppConfig, SettingHint } from "./shared/types";
import SetupPage from "./pages/SetupPage";
import DownloadPage from "./pages/DownloadPage";
import HfModelPage from "./pages/HfModelPage";
import RunPage from "./pages/RunPage";
import StatusPage from "./pages/StatusPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";

type Page = 'setup' | 'download' | 'hf-model' | 'run' | 'status' | 'diagnostics';

interface AppSharedState {
  config: AppConfig | null;
  selectedHfRepo: string | null;
  selectedModelPath: string | null;
  appliedHints: SettingHint[] | null;
}

export default function App() {
  const [page, setPage] = useState<Page>('setup');
  const [shared, setShared] = useState<AppSharedState>({
    config: null,
    selectedHfRepo: null,
    selectedModelPath: null,
    appliedHints: null,
  });

  useEffect(() => {
    getConfig().then(config => setShared(s => ({ ...s, config }))).catch(console.error);
  }, []);

  const updateConfig = useCallback((config: AppConfig) => {
    setShared(s => ({ ...s, config }));
  }, []);

  const selectHfRepo = useCallback((repoId: string) => {
    setShared(s => ({ ...s, selectedHfRepo: repoId }));
    setPage('hf-model');
  }, []);

  const selectModel = useCallback((modelPath: string) => {
    setShared(s => ({ ...s, selectedModelPath: modelPath }));
    setPage('run');
  }, []);

  const applyHints = useCallback((hints: SettingHint[]) => {
    setShared(s => ({ ...s, appliedHints: hints }));
  }, []);

  const clearAppliedHints = useCallback(() => {
    setShared(s => ({ ...s, appliedHints: null }));
  }, []);

  const goToRun = useCallback(() => {
    setPage('run');
  }, []);
  const tabs: { id: Page; label: string }[] = [
    { id: 'setup', label: 'Setup' },
    { id: 'download', label: 'Download' },
    { id: 'hf-model', label: 'Model Detail' },
    { id: 'run', label: 'Run' },
    { id: 'status', label: 'Status' },
    { id: 'diagnostics', label: 'Diagnostics' },
  ];

  return (
    <div className="app">
      <nav className="nav-bar">
        <span className="nav-title">llamaUI</span>
        {tabs.map(t => (
          <button
            key={t.id}
            className={`nav-tab ${page === t.id ? 'active' : ''}`}
            onClick={() => setPage(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <main className="main-content">
        {page === 'setup' && (
          <SetupPage config={shared.config} onConfigUpdate={updateConfig} />
        )}
        {page === 'download' && (
          <DownloadPage config={shared.config} onSelectRepo={selectHfRepo} onSelectModel={selectModel} />
        )}
        {page === 'hf-model' && (
          <HfModelPage
            repoId={shared.selectedHfRepo}
            config={shared.config}
            onApplyHints={applyHints}
            onGoToRun={goToRun}
          />
        )}
        {page === 'run' && (
          <RunPage
            config={shared.config}
            initialModelPath={shared.selectedModelPath}
            appliedHints={shared.appliedHints}
            onAppliedHintsConsumed={clearAppliedHints}
          />
        )}
        {page === 'status' && (
          <StatusPage config={shared.config} />
        )}
        {page === 'diagnostics' && (
          <DiagnosticsPage />
        )}
      </main>
    </div>
  );
}