// End-to-end tests: real browser, real API, throw-away database.
//
//   npx playwright install chromium   (once)
//   npm run test:e2e
//
// Both servers run on "localhost" so the API's SameSite session cookie is
// treated as same-site, exactly as in a real deployment behind one domain.
import { defineConfig, devices } from '@playwright/test';
import os from 'node:os';
import path from 'node:path';

const runId = `${Date.now()}`;
const tmp = path.join(os.tmpdir(), `ai-crms-e2e-${runId}`).replace(/\\/g, '/');
const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // PW_CHANNEL=msedge (or chrome) uses an installed browser instead of
  // downloading Playwright's bundled Chromium.
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel: process.env.PW_CHANNEL || undefined } }],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host localhost --port 8000`,
      cwd: '../backend',
      url: 'http://localhost:8000/api/health/ready',
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        APP_ENV: 'development',
        SECRET_KEY: 'e2e-only-secret-key-not-for-real-use-0123456789',
        DATABASE_URL: `sqlite:///${tmp}-db.sqlite`,
        AI_CRMS_MODEL_DIR: `${tmp}-models`,
        SEED_DEMO_DATA: 'true',
        CORS_ORIGINS: 'http://localhost:5173',
        RATE_LIMIT_AUTH_PER_MINUTE: '1000',
        LOG_LEVEL: 'WARNING',
      },
    },
    {
      command: 'npm run dev -- --host localhost --port 5173 --strictPort',
      url: 'http://localhost:5173',
      timeout: 120_000,
      reuseExistingServer: false,
      env: { VITE_API_URL: 'http://localhost:8000' },
    },
  ],
});
