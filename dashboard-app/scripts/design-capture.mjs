import { chromium } from 'playwright';
import { mkdir, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = join(__dirname, '..');
const outDir = join(rootDir, 'docs/screenshots/design-capture');

const mockUrl = process.env['MOCK_URL'] || 'http://127.0.0.1:8765/design-system.html';
const storybookUrl = process.env['STORYBOOK_URL'] || 'http://127.0.0.1:6006';

const viewport = { width: 1280, height: 900 };

const components = [
  { id: 'accordion', story: 'primitives-accordion--first-open', open: true },
  { id: 'avatar', story: 'primitives-avatar--default' },
  { id: 'badge', story: 'ui-status--default' },
  { id: 'button', story: 'ui-button--all-variants' },
  { id: 'checkbox', story: 'ui-checkbox--default' },
  { id: 'dropdown', story: 'primitives-dropdown--open', open: true },
  { id: 'input', story: 'ui-input--text' },
  { id: 'popover', story: 'primitives-popover--open', open: true },
  { id: 'progress', story: 'ui-progress--default' },
  { id: 'radio', story: 'ui-radio--default' },
  { id: 'separator', story: 'ui-separator--default' },
  { id: 'slider', story: 'primitives-slider--default' },
  { id: 'switch', story: 'ui-switch--default' },
  { id: 'tabs', story: 'primitives-tabs--default' },
  { id: 'toast', story: 'primitives-toast--host', open: true },
  { id: 'tooltip', story: 'ui-tooltip--default' },
  { id: 'dialog', story: 'ui-dialog--opens-on-trigger', open: true },
  { id: 'live-indicator', story: 'primitives-liveindicator--default' },
];

async function captureComponent(page, name, mockAnchor, storyPath, opts = {}) {
  const componentDir = join(outDir, name);
  await mkdir(componentDir, { recursive: true });

  const mockFile = join(componentDir, `${name}-mock.png`);
  const storyFile = join(componentDir, `${name}-storybook.png`);

  // Mock screenshot
  await page.goto(`${mockUrl}#${mockAnchor}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const anchor = page.locator(`#${mockAnchor}`);
  await anchor.scrollIntoViewIfNeeded().catch(() => {});
  const section = await anchor.boundingBox();
  if (section && section.width > 0 && section.height > 0) {
    await page.screenshot({
      path: mockFile,
      clip: { x: 0, y: section.y, width: section.width, height: section.height + 24 },
    });
  } else {
    await page.screenshot({ path: mockFile, fullPage: false });
  }

  // Storybook screenshot
  await page.goto(`${storybookUrl}/iframe.html?id=${storyPath}&viewMode=story`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  if (opts.open) {
    await page.waitForTimeout(name === 'toast' ? 550 : 250);
  }
  await page.screenshot({ path: storyFile, fullPage: false });

  console.log(`Captured ${name}: mock → ${mockFile}, storybook → ${storyFile}`);
}

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport });
const page = await context.newPage();

for (const comp of components) {
  await captureComponent(page, comp.id, comp.id, comp.story, { open: comp.open });
}

await context.close();
await browser.close();
console.log(`Design capture complete: ${outDir}`);
