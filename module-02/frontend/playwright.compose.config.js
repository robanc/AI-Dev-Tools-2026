import { defineConfig } from '@playwright/test';
import containerConfig from './playwright.container.config.js';

// Reuse container settings, with no host-side Vite or backend server.
export default defineConfig(containerConfig, {
  use: { ...containerConfig.use, baseURL: 'http://127.0.0.1:8100' },
  projects: [
    { name: 'integration', testMatch: ['compose-integration/*.spec.js'] },
    { name: 'e2e', testMatch: ['e2e/interview.spec.js'] },
  ],
});
