import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    rolldownOptions: {
      output: {
        // Libraries in their own chunks: each stays under Vite's 500 kB warning, and they cache
        // across deploys of the app code. pdf.js is only fetched when a PDF citation is opened.
        codeSplitting: {
          groups: [
            {
              name: 'react',
              test: /node_modules[\\/](react|react-dom|scheduler|react-router)[\\/]/,
            },
            {
              name: 'ui',
              test: /node_modules[\\/](radix-ui|@radix-ui|@tanstack|sonner|lucide-react)[\\/]/,
            },
            { name: 'pdfjs', test: /node_modules[\\/]pdfjs-dist[\\/]/ },
          ],
        },
      },
    },
  },
  server: {
    // The backend's routes have no /api prefix; the proxy strips it, so the browser only ever
    // talks to the Vite origin and there is no CORS in development.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    // Pure-logic tests run in node; component tests opt into jsdom with a
    // `// @vitest-environment jsdom` comment at the top of the file.
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
  },
})
