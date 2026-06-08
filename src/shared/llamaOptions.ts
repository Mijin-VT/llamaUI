import type { LlamaSettings } from './types';

export type OptionCategory = 'model' | 'server' | 'sampling' | 'performance' | 'advanced';
export type OptionValueType = 'string' | 'number' | 'boolean' | 'string[]';

export interface LlamaOption {
  flag: string;
  aliases: string[];
  valueType: OptionValueType;
  category: OptionCategory;
  defaultValue?: string;
  envVar?: string;
  tooltip: string;
  restartRequired: boolean;
  settingKey?: keyof LlamaSettings;
}

export const LLAMA_OPTIONS: LlamaOption[] = [
  // ── Model ────────────────────────────────────────────────────────────
  {
    flag: '-m',
    aliases: ['--model'],
    valueType: 'string',
    category: 'model',
    tooltip: 'Path to the GGUF model file',
    restartRequired: true,
  },
  {
    flag: '--ctx-size',
    aliases: ['-c'],
    valueType: 'number',
    category: 'model',
    defaultValue: '512',
    tooltip: 'Size of the prompt context (0 = loaded from model)',
    restartRequired: true,
    settingKey: 'ctx_size',
  },
  {
    flag: '--n-gpu-layers',
    aliases: ['-ngl', '--gpu-layers'],
    valueType: 'number',
    category: 'model',
    defaultValue: '0',
    tooltip: 'Number of layers to offload to GPU (-1 = all, 99 = auto-detect)',
    restartRequired: true,
    settingKey: 'n_gpu_layers',
  },

  // ── Performance ──────────────────────────────────────────────────────
  {
    flag: '--threads',
    aliases: ['-t'],
    valueType: 'number',
    category: 'performance',
    tooltip: 'Number of threads for generation',
    restartRequired: true,
    settingKey: 'threads',
  },
  {
    flag: '--batch-size',
    aliases: ['-b'],
    valueType: 'number',
    category: 'performance',
    defaultValue: '2048',
    tooltip: 'Batch size for prompt processing',
    restartRequired: true,
    settingKey: 'batch_size',
  },
  {
    flag: '--ubatch-size',
    aliases: [],
    valueType: 'number',
    category: 'performance',
    defaultValue: '512',
    tooltip: 'Micro-batch size for prompt processing',
    restartRequired: true,
    settingKey: 'ubatch_size',
  },
  {
    flag: '--mmap',
    aliases: [],
    valueType: 'boolean',
    category: 'performance',
    defaultValue: 'true',
    tooltip: 'Use memory-mapped file for model loading',
    restartRequired: true,
    settingKey: 'mmap',
  },
  {
    flag: '--mlock',
    aliases: [],
    valueType: 'boolean',
    category: 'performance',
    tooltip: 'Force system to keep model in RAM (mlock)',
    restartRequired: true,
    settingKey: 'mlock',
  },
  {
    flag: '--fit',
    aliases: [],
    valueType: 'string',
    category: 'performance',
    tooltip: 'Auto-tune to fit available resources: "on" or "off"',
    restartRequired: true,
  },

  // ── Server ───────────────────────────────────────────────────────────
  {
    flag: '--host',
    aliases: [],
    valueType: 'string',
    category: 'server',
    defaultValue: '127.0.0.1',
    tooltip: 'IP address to bind the server to',
    restartRequired: true,
    settingKey: 'host',
  },
  {
    flag: '--port',
    aliases: [],
    valueType: 'number',
    category: 'server',
    defaultValue: '8080',
    tooltip: 'Port to listen on',
    restartRequired: true,
    settingKey: 'port',
  },
  {
    flag: '--parallel',
    aliases: ['-p'],
    valueType: 'number',
    category: 'server',
    defaultValue: '1',
    tooltip: 'Number of parallel sequences (slots)',
    restartRequired: true,
    settingKey: 'parallel',
  },

  // ── Sampling ─────────────────────────────────────────────────────────
  {
    flag: '--temp',
    aliases: [],
    valueType: 'number',
    category: 'sampling',
    defaultValue: '0.8',
    tooltip: 'Temperature for sampling (0 = greedy)',
    restartRequired: false,
    settingKey: 'temp',
  },
  {
    flag: '--top-k',
    aliases: [],
    valueType: 'number',
    category: 'sampling',
    defaultValue: '40',
    tooltip: 'Top-K sampling parameter',
    restartRequired: false,
    settingKey: 'top_k',
  },
  {
    flag: '--top-p',
    aliases: [],
    valueType: 'number',
    category: 'sampling',
    defaultValue: '0.95',
    tooltip: 'Top-P (nucleus) sampling parameter',
    restartRequired: false,
    settingKey: 'top_p',
  },
  {
    flag: '--min-p',
    aliases: [],
    valueType: 'number',
    category: 'sampling',
    defaultValue: '0.05',
    tooltip: 'Min-P sampling parameter',
    restartRequired: false,
    settingKey: 'min_p',
  },
  {
    flag: '--repeat-penalty',
    aliases: [],
    valueType: 'number',
    category: 'sampling',
    defaultValue: '1.1',
    tooltip: 'Penalize repeat tokens',
    restartRequired: false,
    settingKey: 'repeat_penalty',
  },
  {
    flag: '--seed',
    aliases: [],
    valueType: 'number',
    category: 'sampling',
    tooltip: 'RNG seed (-1 = random)',
    restartRequired: false,
    settingKey: 'seed',
  },

  // ── Advanced ─────────────────────────────────────────────────────────
  {
    flag: '--verbose',
    aliases: ['-v'],
    valueType: 'boolean',
    category: 'advanced',
    tooltip: 'Enable verbose output',
    restartRequired: false,
    settingKey: 'verbose',
  },
  {
    flag: '--hf-repo',
    aliases: ['-hf'],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'Hugging Face model repository (e.g. user/model)',
    restartRequired: true,
    settingKey: 'hf_repo',
  },
  {
    flag: '--hf-file',
    aliases: ['-hff'],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'Specific file in HF repo to load',
    restartRequired: true,
    settingKey: 'hf_file',
  },
  {
    flag: '--hf-token',
    aliases: ['-hft'],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'Hugging Face API token',
    restartRequired: true,
    envVar: 'HF_TOKEN',
  },
  {
    flag: '--fit-target',
    aliases: [],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'Target for --fit: "gpu", "cpu", or "all"',
    restartRequired: true,
  },
  {
    flag: '--split-mode',
    aliases: [],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'GPU split mode: "none", "layer", "row"',
    restartRequired: true,
  },
  {
    flag: '--tensor-split',
    aliases: [],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'Fraction of tensors to offload to each GPU (comma-separated)',
    restartRequired: true,
  },
  {
    flag: '--main-gpu',
    aliases: [],
    valueType: 'number',
    category: 'advanced',
    tooltip: 'Main GPU index for split-mode',
    restartRequired: true,
  },
  {
    flag: '--device',
    aliases: [],
    valueType: 'string',
    category: 'advanced',
    tooltip: 'Comma-separated list of devices to use',
    restartRequired: true,
  },
];
