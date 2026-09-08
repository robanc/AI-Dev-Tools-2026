import { defineConfig } from '@playwright/test';

// Test an already-running container; do not start host-side backend/Vite servers.
export default defineConfig({
  testDir: '.', testMatch: ['e2e/interview.spec.js', 'container-e2e/*.spec.js'],
  workers: 1, timeout: 60000,
  use: { baseURL: process.env.CONTAINER_URL || 'http://127.0.0.1:8000',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
});
