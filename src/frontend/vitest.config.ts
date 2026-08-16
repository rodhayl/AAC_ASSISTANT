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
      reporter: ['text', 'text-summary'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/types/**',
        'src/**/*.d.ts',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: {
        // Floor at the current honest src-only coverage so future work cannot
        // silently erode unit/component coverage. GUI-heavy pages/components
        // are additionally exercised by the Playwright e2e suite in CI.
        statements: 50,
        branches: 40,
        functions: 45,
        lines: 50,
      },
    },
  },
})
