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

test('theme selection persists across direct navigation', async ({ page }) => {
  await page.goto('/');
  const html = page.locator('html');

  await page.getByRole('group', { name: 'Choose theme' }).getByRole('button', { name: 'Nocturne' }).click();
  await expect(html).toHaveAttribute('data-theme', 'nocturne');

  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: 'Reports', level: 1 }).first()).toBeVisible();
  await expect(html).toHaveAttribute('data-theme', 'nocturne');
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
    const region = document.querySelector('#automation-region');
    if (!region) return false;
    const regionBox = region.getBoundingClientRect();
    const names = [...region.querySelectorAll('.svc__name')];
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

  await page.setViewportSize({ width: 1440, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expectAutomationReadable(page);

  await page.setViewportSize({ width: 1600, height: 900 });
  await expectNoHorizontalOverflow(page);
  await expectAutomationReadable(page);
});

const THEMES = ['nocturne', 'tokyo-night', 'github-dark-pro'] as const;
const THEME_BUTTON: Record<(typeof THEMES)[number], string> = {
  nocturne: 'Nocturne',
  'tokyo-night': 'Tokyo Night',
  'github-dark-pro': 'GitHub Dark Pro',
};

test('theme picker stays in sync with the applied theme and theme-color', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => localStorage.removeItem('media-ui-theme'));
  await page.reload();

  const html = page.locator('html');
  const picker = page.getByRole('group', { name: 'Choose theme' });
  await expect(html).toHaveAttribute('data-theme', 'github-dark-pro');
  await expect(picker.getByRole('button', { name: 'GitHub Dark Pro' })).toHaveAttribute('aria-pressed', 'true');

  await expect.poll(async () =>
    page.evaluate(() => {
      const surface = getComputedStyle(document.documentElement)
        .getPropertyValue('--mm-color-surface-0')
        .trim();
      const themeColor = document.querySelector('meta[name="theme-color"]')?.getAttribute('content');
      return surface.length > 0 && surface === themeColor;
    }),
  ).toBe(true);

  await page.evaluate(() => localStorage.setItem('media-ui-theme', 'tokyo-night'));
  await page.reload();
  await expect(html).toHaveAttribute('data-theme', 'tokyo-night');
  await expect(picker.getByRole('button', { name: 'Tokyo Night' })).toHaveAttribute('aria-pressed', 'true');

  for (const theme of THEMES) {
    await picker.getByRole('button', { name: THEME_BUTTON[theme] }).click();
    await expect(html).toHaveAttribute('data-theme', theme);
    await expect(picker.getByRole('button', { name: THEME_BUTTON[theme] })).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(async () =>
      page.evaluate(() => {
        const surface = getComputedStyle(document.documentElement)
          .getPropertyValue('--mm-color-surface-0')
          .trim();
        const themeColor = document.querySelector('meta[name="theme-color"]')?.getAttribute('content');
        return surface.length > 0 && surface === themeColor;
      }),
    ).toBe(true);
    expect(await page.evaluate(() => localStorage.getItem('media-ui-theme'))).toBe(theme);
  }
});
