import { expect, test } from '@playwright/test';

const forbiddenDestructiveControl = /\b(delete|remove|execute|confirm deletion|clean now)\b/i;

test('Storage Guardian stays idle until explicit preview and exposes no destructive control', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/storage?scenario=storage-ready');

  await expect(page).toHaveTitle('Storage Guardian | Media Manager');
  await expect(page.getByRole('heading', { name: 'Storage Guardian' })).toBeVisible();
  await expect(page.getByText('Simulation only', { exact: false })).toBeVisible();
  await expect(page.getByTestId('cleanup-candidate-list')).toHaveCount(0);
  await expect(page.getByText('Nothing runs automatically.')).toBeVisible();

  await page.getByTestId('run-cleanup-preview').getByRole('button').click();
  await expect(page.getByTestId('cleanup-candidate-list')).toBeVisible();
  await expect(page.getByText('Dune: Part Two', { exact: true })).toBeVisible();
  await expect(page.getByText('94 GB', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Target restored', { exact: true })).toBeVisible();

  const labels = await page.getByRole('button').allTextContents();
  expect(labels.some((label) => forbiddenDestructiveControl.test(label))).toBe(false);
  await expectNoHorizontalOverflow(page);
});

test('Storage Guardian mobile composition uses rules summary and tabs without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1320 });
  await page.goto('/storage?scenario=storage-ready');
  await page.getByTestId('run-cleanup-preview').getByRole('button').click();

  await expect(page.getByRole('heading', { name: 'Storage Guardian' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Rules summary' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Suggested' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('Dune: Part Two', { exact: true })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('target-met, insufficient, degraded and Keep states remain simulation-only', async ({ page }) => {
  await page.goto('/storage?scenario=storage-target-met');
  await page.getByTestId('run-cleanup-preview').getByRole('button').click();
  await expect(page.getByText(/free-space target is already met/i)).toBeVisible();
  await page.getByRole('radio', { name: 'All matches' }).click();
  await expect(page.getByText('Dune: Part Two', { exact: true })).toBeVisible();

  await page.goto('/storage?scenario=storage-insufficient');
  await page.getByTestId('run-cleanup-preview').getByRole('button').click();
  await expect(page.getByText(/short/i).first()).toBeVisible();

  await page.goto('/storage?scenario=storage-degraded');
  await page.getByTestId('run-cleanup-preview').getByRole('button').click();
  await expect(page.getByText('Degraded preview', { exact: true })).toBeVisible();
  await page.getByRole('radio', { name: 'Needs review' }).click();
  await expect(page.getByTestId('cleanup-unresolved-list')).toContainText('Alternate cut');

  await page.getByRole('radio', { name: 'All matches' }).click();
  const first = page.getByTestId('cleanup-candidate').first();
  await first.getByRole('button', { name: 'Keep' }).click();
  await expect(page.getByText(/Settings changed\. Run preview again/i)).toBeVisible();
  const persisted = await page.evaluate(() => JSON.parse(localStorage.getItem('lumen.storageGuardian.pins.v1') ?? '{}'));
  expect(persisted.schemaVersion).toBe(1);
  expect(persisted.ids).toHaveLength(1);

  const labels = await page.getByRole('button').allTextContents();
  expect(labels.some((label) => forbiddenDestructiveControl.test(label))).toBe(false);
});

test('existing storage mini-card is the only shell entry point', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const primary = page.locator('.sidebar__nav');
  await expect(primary.locator('a')).toHaveCount(4);
  const storage = page.getByTestId('storage-mini-card');
  await expect(storage).toHaveAttribute('href', '/storage');
  await storage.click();
  await expect(page.getByRole('heading', { name: 'Storage Guardian' })).toBeVisible();
});

async function expectNoHorizontalOverflow(page: import('@playwright/test').Page): Promise<void> {
  await expect.poll(async () =>
    page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
}
