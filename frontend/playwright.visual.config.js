// Screenshot capture for design review; reuses the E2E servers.
import base from './playwright.config.js';
import { defineConfig } from '@playwright/test';

export default defineConfig({
  ...base,
  testDir: './tests/visual',
  use: { ...base.use, viewport: { width: 1440, height: 900 } },
});
