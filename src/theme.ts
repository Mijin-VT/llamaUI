import { createTheme, MantineColorsTuple } from '@mantine/core';

/* ── Color palette ─────────────────────────────────────── */

const dark: MantineColorsTuple = [
  '#0a0c10', // 0  deepest inset
  '#0f1117', // 1  app bg
  '#161922', // 2  surface
  '#1c1f2a', // 3  surface hover
  '#1e222d', // 4  elevated
  '#2a2e3b', // 5  border
  '#9aa0b2', // 6  secondary text
  '#e2e4e9', // 7  primary text
  '#ffffff', // 8
  '#ffffff', // 9
];

const blue: MantineColorsTuple = [
  '#e0f2fe',
  '#bae6fd',
  '#7dd3fc',
  '#38bdf8',
  '#0ea5e9',
  '#0284c7',
  '#0369a1',
  '#075985',
  '#0c4a6e',
  '#082f49',
];

const green: MantineColorsTuple = [
  '#dcfce7',
  '#bbf7d0',
  '#86efac',
  '#4ade80',
  '#22c55e',
  '#16a34a',
  '#15803d',
  '#166534',
  '#14532d',
  '#052e16',
];

const red: MantineColorsTuple = [
  '#fee2e2',
  '#fecaca',
  '#fca5a5',
  '#f87171',
  '#ef4444',
  '#dc2626',
  '#b91c1c',
  '#991b1b',
  '#7f1d1d',
  '#450a0a',
];

const amber: MantineColorsTuple = [
  '#fef3c7',
  '#fde68a',
  '#fcd34d',
  '#fbbf24',
  '#f59e0b',
  '#d97706',
  '#b45309',
  '#92400e',
  '#78350f',
  '#451a03',
];

/* ── Theme ─────────────────────────────────────────────── */

export const appTheme = createTheme({
  primaryColor: 'blue',
  primaryShade: 4,
  colors: { dark, blue, green, red, amber },
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
  fontFamilyMonospace: 'JetBrains Mono, Consolas, Monaco, Courier New, monospace',
  defaultRadius: 'md',
  radius: {
    xs: '2px',
    sm: '4px',
    md: '6px',
    lg: '8px',
    xl: '12px',
  },
  spacing: {
    xs: '4px',
    sm: '6px',
    md: '10px',
    lg: '16px',
    xl: '24px',
  },
  fontSizes: {
    xs: '11px',
    sm: '12px',
    md: '13px',
    lg: '14px',
    xl: '16px',
  },
  headings: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
    sizes: {
      h1: { fontSize: '20px', fontWeight: '600', lineHeight: '1.3' },
      h2: { fontSize: '16px', fontWeight: '600', lineHeight: '1.3' },
      h3: { fontSize: '14px', fontWeight: '600', lineHeight: '1.3' },
      h4: { fontSize: '13px', fontWeight: '600', lineHeight: '1.3' },
    },
  },
  components: {
    Button: {
      defaultProps: {
        size: 'sm',
      },
      styles: {
        root: {
          fontWeight: 500,
        },
      },
    },
    Input: {
      defaultProps: {
        size: 'sm',
      },
    },
    Select: {
      defaultProps: {
        size: 'sm',
      },
    },
    Card: {
      defaultProps: {
        padding: 'lg',
        radius: 'md',
        withBorder: true,
      },
    },
    Badge: {
      defaultProps: {
        size: 'sm',
        radius: 'sm',
      },
    },
  },
});
