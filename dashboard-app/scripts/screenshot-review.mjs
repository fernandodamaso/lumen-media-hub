import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '../docs/screenshots/review');
await mkdir(outDir, { recursive: true });

const baseUrl = process.env['BASE_URL'] || 'http://127.0.0.1:4200';
const viewports = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900', width: 1440, height: 900 },
];

const routes = ['/', '/reports', '/discover'];

const browser = await chromium.launch({ headless: true });

for (const viewport of viewports) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();

  for (const route of routes) {
    const name = route === '/' ? 'home' : route.slice(1);
    await page.goto(`${baseUrl}${route}`, { waitUntil: 'load' });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: join(outDir, `${name}-${viewport.name}.png`), fullPage: false });
    console.log(`Captured ${name}-${viewport.name}.png`);
  }

  await context.close();
}

await browser.close();
console.log(`Screenshots saved to ${outDir}`);
