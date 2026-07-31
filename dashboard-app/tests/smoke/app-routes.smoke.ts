import { test, expect } from '@playwright/test';

const routes = [
  { path: '/', title: 'Dashboard | Media Manager', heading: 'Dashboard' },
  { path: '/dashboard', title: 'Dashboard | Media Manager', heading: 'Dashboard' },
  { path: '/library', title: 'Library | Media Manager', heading: 'Library' },
  { path: '/reports', title: 'Reports | Media Manager', heading: 'Reports' },
  { path: '/discover', title: 'Discover | Media Manager', heading: 'Discover' },
];

for (const route of routes) {
  test(`direct navigation to ${route.path} renders expected page`, async ({ page }) => {
    await page.goto(route.path);
    const main = page.locator('main').first();
    await expect(main).toBeVisible();
    await expect(main).toContainText(route.heading);
    await expect(page).toHaveTitle(route.title, { timeout: 15_000 });
  });
}

test('unknown route falls back to dashboard', async ({ page }) => {
  await page.goto('/nonexistent-route-xyz');
  const main = page.locator('main').first();
  await expect(main).toBeVisible();
  await expect(main).toContainText('Dashboard');
  await expect(page).toHaveTitle('Dashboard | Media Manager', { timeout: 15_000 });
});

test('applies the single Lumen palette with matching theme-color', async ({ page }) => {
  await page.goto('/');
  expect(await page.locator('html').getAttribute('data-theme')).toBeNull();
  await expect.poll(async () =>
    page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--mm-color-surface-0').trim(),
    ),
  ).toBe('#0a0a0f');
  expect(await page.locator('meta[name="theme-color"]').getAttribute('content')).toBe('#0a0a0f');
});

test('sidebar navigation links are present', async ({ page }) => {
  await page.goto('/');
  const workspaceNav = page.locator('.sidebar__nav');
  await expect(workspaceNav).toBeVisible();
  await expect(workspaceNav.locator('a')).toHaveCount(4);
  await expect(workspaceNav).toContainText('Dashboard');
  await expect(workspaceNav).toContainText('Library');
  await expect(workspaceNav).toContainText('Reports');
  await expect(workspaceNav).toContainText('Discover');
});

async function expectNoHorizontalOverflow(page: import('@playwright/test').Page): Promise<void> {
  await expect.poll(async () =>
    page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
}

async function expectAutomationReadable(page: import('@playwright/test').Page): Promise<void> {
  const readable = await page.evaluate(() => {
    const region = document.querySelector('[data-testid="rr-health"]');
    if (!region) return false;
    const regionBox = region.getBoundingClientRect();
    const names = [...region.querySelectorAll('.svc-name')];
    if (names.length === 0) return false;
    return names.every((name) => {
      const box = name.getBoundingClientRect();
      return box.width > 0 && box.right <= regionBox.right + 1;
    });
  });
  expect(readable).toBe(true);
}

test('dashboard layout stays within the viewport at mobile and desktop widths', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  await expectNoHorizontalOverflow(page);
  await expect(page.getByRole('button', { name: 'Add media' })).toBeVisible();
  await expect(page.locator('.dl-stats')).toBeVisible();
  expect(await page.locator('.dl-stats').evaluate((element) => element.getBoundingClientRect().right <= window.innerWidth)).toBe(true);

  await page.setViewportSize({ width: 1440, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expectAutomationReadable(page);

  await page.setViewportSize({ width: 1600, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expectAutomationReadable(page);
});
