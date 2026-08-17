import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './vitest.setup.ts',
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
