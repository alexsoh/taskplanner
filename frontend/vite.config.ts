import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: path.resolve(__dirname, '..', 'static'),
    emptyOutDir: true,
  },
  server: {
    port: 3200,
    proxy: {
      '/api': 'http://127.0.0.1:8200',
    },
  },
  test: {
    environment: 'node',
  },
})
