import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  root: fileURLToPath(new URL('./demo', import.meta.url)),
  base: '/demo-app/',
  plugins: [react(), tailwindcss()],
  build: {
    emptyOutDir: true,
    outDir: fileURLToPath(new URL('../website/public/demo-app', import.meta.url)),
  },
});
