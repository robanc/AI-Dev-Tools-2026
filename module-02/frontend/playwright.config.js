import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:5174', channel: process.env.PLAYWRIGHT_CHANNEL || undefined },
  webServer: [
    { command: 'uv run --project ../backend uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8001 --no-access-log',
      url: 'http://127.0.0.1:8001/docs', env: { FRONTEND_ORIGINS: 'http://127.0.0.1:5174' }, reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort', url: 'http://127.0.0.1:5174',
      env: { VITE_INTERVIEW_SERVICE: 'real', VITE_API_BASE_URL: 'http://127.0.0.1:8001' }, reuseExistingServer: false },
  ],
});
