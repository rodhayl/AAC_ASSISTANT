import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { readProjectVersion } from './scripts/project-version'

// Tests import src/config.ts, which expects the build-time version injection
// that vite.config.ts performs (see scripts/project-version.ts).
const appVersion = readProjectVersion()

export default defineConfig({
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(appVersion),
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './vitest.setup.ts',
    testTimeout: 15000,
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      'e2e/**',
      '**/e2e/**',
      'playwright/**',
      '**/playwright/**',
      'test-results/**',
      '**/test-results/**',
    ],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        // Locale data files are not executable code.
        'src/**/*.json',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: {
        // Regression guard on the measured application-only baseline.
        lines: 62,
        functions: 55,
        statements: 60,
        branches: 51,
      },
    },
  },
})
