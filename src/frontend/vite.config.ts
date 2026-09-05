import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Backend port is configurable via VITE_BACKEND_PORT (see src/config.ts and
// .env.example); the dev proxy must follow it instead of hardcoding 8086.
const backendPort = process.env.VITE_BACKEND_PORT || '8086'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // Use esbuild for faster minification
    minify: 'esbuild',
    // Enable code splitting
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router'],
          'ui-vendor': ['lucide-react'],
          'dnd-vendor': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
          'state-vendor': ['zustand', 'axios'],
          // Headless primitives + toast layer added by the 2026-08 shadcn/Base
          // UI migration; kept as a separate cacheable chunk so the app's own
          // index chunk stays under the bundle-size budget.
          'base-ui-vendor': ['@base-ui/react', 'sonner'],
        },
      },
    },
    // Optimize chunk size
    chunkSizeWarningLimit: 1000,
  },
  // Server configuration
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.VITE_FRONTEND_PORT || '5176'),
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        secure: false,
      },
    },
    hmr: {
      host: 'localhost',
      port: parseInt(process.env.VITE_FRONTEND_PORT || '5176'),
    },
  },
})
