import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Local dev mirrors production, where the API is same-origin at /api.
    proxy: { '/api': { target: 'http://localhost:3001', changeOrigin: true } },
  },
});
