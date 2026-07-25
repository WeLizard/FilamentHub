import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
  server: {
    port: 3000,
    host: '0.0.0.0', // Слушать на всех интерфейсах (IPv4 и IPv6)
    // Bind-mount с Windows-хоста в контейнер не доставляет события об изменении
    // файлов, из-за чего Vite отдаёт полусобранный модуль до перезапуска. Опрос
    // включается только в контейнере, чтобы не жечь CPU при локальном запуске.
    watch: process.env.CHOKIDAR_USEPOLLING === 'true'
      ? { usePolling: true, interval: 400 }
      : undefined,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
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

