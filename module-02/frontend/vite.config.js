import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], test: { include: ['src/**/*.test.{js,jsx}'], environment: 'jsdom', setupFiles: './src/test/setup.js', clearMocks: true } });
