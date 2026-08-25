import { expect, test } from '@playwright/test';

test('upcoming rail exposes mixed episode/movie releases and both provider calendars', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  const rail = page.getByTestId('rr-upcoming');
  await expect(rail).toBeVisible();
  await expect(rail).toContainText('Cowboy Bebop');
  await expect(rail).toContainText('Dune');
  await expect(rail.getByRole('link', { name: 'Sonarr' })).toHaveAttribute('href', /8989\/calendar$/);
  await expect(rail.getByRole('link', { name: 'Radarr' })).toHaveAttribute('href', /7878\/calendar$/);
});
