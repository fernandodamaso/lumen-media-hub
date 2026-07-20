import { test, expect } from '@playwright/test';

const routes = [
  { path: '/', title: 'Dashboard | Media Manager', heading: 'Dashboard' },
  { path: '/dashboard', title: 'Dashboard | Media Manager', heading: 'Dashboard' },
  { path: '/reports', title: 'Reports | Media Manager', heading: 'Reports' },
  { path: '/discover', title: 'Discover | Media Manager', heading: 'Discover' },
];

for (const route of routes) {
  test(`direct navigation to ${route.path} renders expected page`, async ({ page }) => {
    await page.goto(route.path, { waitUntil: 'networkidle' });
    const main = page.locator('main').first();
    await expect(main).toBeVisible();
    await expect(main).toContainText(route.heading);
    await expect(page).toHaveTitle(route.title, { timeout: 15_000 });
  });
}

test('unknown route falls back to dashboard', async ({ page }) => {
  await page.goto('/nonexistent-route-xyz', { waitUntil: 'networkidle' });
  const main = page.locator('main').first();
  await expect(main).toBeVisible();
  await expect(main).toContainText('Dashboard');
  await expect(page).toHaveTitle('Dashboard | Media Manager', { timeout: 15_000 });
});

test('theme selection persists across direct navigation', async ({ page }) => {
  await page.goto('/');
  const html = page.locator('html');

  await page.getByRole('combobox', { name: 'Choose theme' }).selectOption('nocturne');
  await expect(html).toHaveAttribute('data-theme', 'nocturne');

  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: 'Reports', level: 1 }).first()).toBeVisible();
  await expect(html).toHaveAttribute('data-theme', 'nocturne');
});

test('sidebar navigation links are present', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  const workspaceNav = page.locator('.sidebar__nav');
  await expect(workspaceNav).toBeVisible();
  await expect(workspaceNav.locator('a')).toHaveCount(3);
  await expect(workspaceNav).toContainText('Dashboard');
  await expect(workspaceNav).toContainText('Reports');
  await expect(workspaceNav).toContainText('Discover');
});
