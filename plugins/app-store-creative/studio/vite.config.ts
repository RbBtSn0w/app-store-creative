import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3100,
    host: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
