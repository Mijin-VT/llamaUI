import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import type {
  AppConfig, HfSearchResult, HfModelInfo, ModelCardResponse,
  GgufFileInfo, ModelProfile, LlamaSettings, HardwareInfo,
  ModelRecommendation, ServerStatus, DownloadProgress, FrameworkDiagnostics
} from "./types";

// Config
export async function getConfig(): Promise<AppConfig> {
  return invoke("get_config");
}

export async function updateConfig(config: AppConfig): Promise<void> {
  return invoke("update_config", { config });
}

export async function pickLlamaServerExecutable(): Promise<string | null> {
  return invoke("pick_llama_server_executable");
}

export async function pickModelsDir(): Promise<string | null> {
  return invoke("pick_models_dir");
}

// HF
export async function hfValidateToken(token: string): Promise<string> {
  return invoke("hf_validate_token", { token });
}

export async function hfWhoami(): Promise<string | null> {
  return invoke("hf_whoami");
}

export async function hfSearch(query: string): Promise<HfSearchResult[]> {
  return invoke("hf_search", { query });
}

export async function hfModel(repoId: string): Promise<HfModelInfo> {
  return invoke("hf_model", { repoId });
}

export async function hfModelCard(repoId: string): Promise<ModelCardResponse> {
  return invoke("hf_model_card", { repoId });
}

// Downloads
export async function downloadStart(repoId: string, filename: string): Promise<DownloadProgress> {
  return invoke("download_start", { repoId, filename });
}

export async function downloadCancel(repoId: string, filename: string): Promise<void> {
  return invoke("download_cancel", { repoId, filename });
}

export async function downloadStatus(repoId: string, filename: string): Promise<boolean> {
  return invoke("download_status", { repoId, filename });
}

export function onDownloadProgress(cb: (progress: DownloadProgress) => void): Promise<UnlistenFn> {
  return listen<DownloadProgress>("download-progress", (event) => cb(event.payload));
}

// Models
export async function modelsList(): Promise<GgufFileInfo[]> {
  return invoke("models_list");
}

// Profiles
export async function modelProfileGet(modelPath: string, hfRepo?: string, hfFile?: string): Promise<ModelProfile | null> {
  return invoke("model_profile_get", { modelPath, hfRepo, hfFile });
}

export async function modelProfileSave(profile: ModelProfile): Promise<void> {
  return invoke("model_profile_save", { profile });
}

export async function modelProfileDelete(modelPath: string, hfRepo?: string, hfFile?: string): Promise<void> {
  return invoke("model_profile_delete", { modelPath, hfRepo, hfFile });
}

export async function modelProfileList(): Promise<ModelProfile[]> {
  return invoke("model_profile_list");
}

// Hardware
export async function hardwareScan(): Promise<HardwareInfo> {
  return invoke("hardware_scan");
}

// Recommendations
export async function modelRecommendation(modelSizeBytes: number, hardware: HardwareInfo, settings?: LlamaSettings): Promise<ModelRecommendation> {
  return invoke("model_recommendation", { modelSizeBytes, hardware, settings });
}

// Server
export async function serverStart(modelPath: string, settings: LlamaSettings): Promise<void> {
  return invoke("server_start", { modelPath, settings });
}

export async function serverStop(): Promise<void> {
  return invoke("server_stop");
}

export async function serverStatus(): Promise<ServerStatus> {
  return invoke("server_status");
}

export function onServerLog(cb: (line: string) => void): Promise<UnlistenFn> {
  return listen<string>("server-log", (event) => cb(event.payload));
}


// Diagnostics
export async function frameworkDiagnostics(): Promise<FrameworkDiagnostics> {
  return invoke("framework_diagnostics");
}
export function onServerStarted(cb: (pid: number) => void): Promise<UnlistenFn> {
  return listen<number>("server-started", (event) => cb(event.payload));
}
