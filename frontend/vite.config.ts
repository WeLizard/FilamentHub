import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// https://vite.dev/config/
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000';
const unreferencedPublicSourceMedia = [
  'catalog-presets.png',
  'orcaslicer-win-main.png',
  'presets-sync.png',
  'step-download-orca.JPG',
];

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'exclude-unreferenced-public-source-media',
      apply: 'build',
      async closeBundle() {
        await Promise.all(unreferencedPublicSourceMedia.map((fileName) => rm(
          fileURLToPath(new URL(`./dist/download-media/${fileName}`, import.meta.url)),
          { force: true },
        )));
      },
    },
  ],
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
  server: {
    port: 3000,
    host: '0.0.0.0', // Слушать на всех интерфейсах (IPv4 и IPv6)
    watch: process.env.CHOKIDAR_USEPOLLING === 'true'
      ? { usePolling: true, interval: 400 }
      : undefined,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        ws: true,
        timeout: 180000, // 3 минуты для длительных операций (миграции)
      },
      '/uploads': {
        target: proxyTarget,
        changeOrigin: true,
        timeout: 180000,
      },
      '/wiki_content': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});

