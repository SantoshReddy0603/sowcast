import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/v1': process.env.SOWCAST_API_TARGET || 'http://127.0.0.1:8000',
      '/health': process.env.SOWCAST_API_TARGET || 'http://127.0.0.1:8000',
    },
  },
});
