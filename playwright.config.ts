import { defineConfig } from '@playwright/test';

const port = Number(process.env['SMOKE_PORT'] ?? 4301);

export default defineConfig({
  testDir: './tests/smoke',
  testMatch: '**/*.smoke.ts',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npx ng serve dashboard --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
