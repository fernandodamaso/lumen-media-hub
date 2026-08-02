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

test('discover segmented filters preserve dataset behavior without overflow', async ({ page }) => {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/discover');
    await expect(page.getByRole('main')).toContainText('Discover');
    await expect(page.getByRole('radiogroup', { name: 'Discover sources' })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const trakt = page.getByRole('radio', { name: 'Trakt', exact: true });
    await trakt.click();
    await expect(trakt).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByText('Trakt Horizon', { exact: true })).toBeVisible();
    await expect(page.locator('.discover-count')).toHaveText('2 titles');
    await expectNoHorizontalOverflow(page);

    const shows = page.getByRole('radio', { name: 'Shows', exact: true });
    await shows.click();
    await expect(shows).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByText('Trakt Relay', { exact: true })).toBeVisible();
    await expect(page.getByText('Trakt Horizon', { exact: true })).toBeHidden();
    await expect(page.locator('.discover-count')).toHaveText('2 titles');
  }
});

test('library segmented filters preserve counts and dataset without overflow', async ({ page }) => {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/library');
    await expect(page.getByRole('main')).toContainText('Library');
    await expect(page.locator('.pagehead__sub')).toContainText('8 titles');
    await expectNoHorizontalOverflow(page);

    const movies = page.getByRole('radio', { name: 'Movies', exact: true });
    await movies.click();
    await expect(movies).toHaveAttribute('aria-checked', 'true');
    const grid = page.locator('mm-library-poster-grid');
    await expect(grid.locator('mm-media-card')).toHaveCount(4);
    await expect(grid.getByText('Dune', { exact: true }).first()).toBeVisible();
    await expect(grid.getByText('Cowboy Bebop', { exact: true })).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
  }
});

test('command palette traps focus and restores it to the search trigger', async ({ page }) => {
  await page.goto('/');
  const trigger = page.getByTestId('topbar-search');
  await trigger.focus();
  await trigger.click();
  const dialog = page.locator('dialog[aria-label="Command palette"]');
  await expect(dialog).toBeVisible();
  const search = page.getByRole('searchbox', { name: 'Search commands' });
  await expect(search).toBeFocused();

  const focusables = dialog.locator('input, button, [href], select, textarea, [tabindex]:not([tabindex="-1"])');
  const firstFocusable = focusables.first();
  const lastFocusable = focusables.last();
  await expect(focusables).toHaveCount(10);
  await lastFocusable.focus();
  await page.keyboard.press('Tab');
  await expect(firstFocusable).toBeFocused();
  await firstFocusable.focus();
  await page.keyboard.press('Shift+Tab');
  await expect(lastFocusable).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
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
  for (const [width, height] of [[390, 844], [1440, 900], [1600, 900]]) {
    await page.setViewportSize({ width, height });
    await page.goto('/');

    await expect(page.getByRole('main')).toContainText('Dashboard');
    await expectNoHorizontalOverflow(page);
    await expect(page.getByRole('button', { name: 'Add media' })).toBeVisible();
    await expect(page.getByTestId('hero-play')).toHaveAttribute('target', '_blank');
    await expect(page.getByTestId('hero-play')).toHaveAttribute('href', /.+/);
    await expect(page.getByTestId('hero-details')).toHaveAttribute('href', /\/library$/);

    if (width >= 1440) {
      const storage = page.locator('[data-testid="storage-mini-card"] [role="progressbar"]');
      await expect(storage).toHaveAttribute('aria-label', 'Storage 67% used');
      await expect(storage).toHaveAttribute('aria-valuenow', '67');
    }

    const continueCard = page.locator('[data-testid="cw-rail"] mm-media-card').first();
    await expect(continueCard).toBeVisible();
    await expect(continueCard.locator('.mm-media-card__hit')).toHaveAttribute('href', /.+/);
    await expect(continueCard).toContainText('The Expanse');
    await expect(continueCard.locator('.mm-media-card__play-cue')).toBeVisible();
    await expect(continueCard.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');

    const recentCard = page.locator('[data-testid="recent-rail"] mm-media-card').first();
    await expect(recentCard).toBeVisible();
    await expect(recentCard.locator('.mm-media-card__hit')).toHaveAttribute('href', /.+/);
    const railForward = page.getByRole('button', { name: 'Scroll Continue Watching forward' });
    await expect(railForward).toBeVisible();
    await railForward.click();

    await expect(page.locator('.dl-stats')).toBeVisible();
    expect(await page.locator('.dl-stats').evaluate((element) => element.getBoundingClientRect().right <= window.innerWidth)).toBe(true);
    if (width >= 1440) await expectAutomationReadable(page);
  }
});

test('right rail toggle exposes its target and follows responsive motion rules', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  const toggle = page.locator('[data-testid="topbar-toggle-rail"] button');
  const rail = page.locator('#activity-rail');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(toggle).toHaveAttribute('aria-controls', 'activity-rail');
  await expect(rail).toBeVisible();
  expect(await page.locator('.shell').evaluate((element) => getComputedStyle(element).transitionProperty)).toContain(
    'grid-template-columns',
  );

  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(await rail.evaluate((element) => getComputedStyle(element).transitionProperty)).toContain('visibility');
  expect(await rail.evaluate((element) => getComputedStyle(element).transitionDelay)).toContain('0.2s');
  await expect.poll(async () => rail.evaluate((element) => getComputedStyle(element).visibility)).toBe('hidden');

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  expect(await page.locator('.shell').evaluate((element) => getComputedStyle(element).transitionDuration)).toBe('0s');

  await page.setViewportSize({ width: 1200, height: 900 });
  await expect(toggle).toBeHidden();
  await expect(rail).toBeHidden();
});
