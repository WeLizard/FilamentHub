import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    host: '0.0.0.0', // Слушать на всех интерфейсах (IPv4 и IPv6)
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 180000, // 3 минуты для длительных операций (миграции)
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        timeout: 180000,
      },
      '/wiki': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});

