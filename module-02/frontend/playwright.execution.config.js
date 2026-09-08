import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './execution-e2e', workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:4175', channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
  webServer: {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4175 --strictPort',
    env: { VITE_INTERVIEW_SERVICE: 'mock' }, url: 'http://127.0.0.1:4175', reuseExistingServer: false,
  },
});
