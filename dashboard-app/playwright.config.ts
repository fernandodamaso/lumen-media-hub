import { defineConfig } from '@playwright/test';

const port = Number(process.env['SMOKE_PORT'] ?? 4301);
const baseURL = process.env['SMOKE_BASE_URL'] ?? `http://127.0.0.1:${port}`;
const useExternalServer = !!process.env['SMOKE_BASE_URL'];

export default defineConfig({
  testDir: './tests/smoke',
  testMatch: '**/*.smoke.ts',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL,
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: useExternalServer
    ? undefined
    : {
        command: `npx ng serve dashboard --host 127.0.0.1 --port ${port}`,
        url: `http://127.0.0.1:${port}`,
        reuseExistingServer: false,
        timeout: 180_000,
      },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
