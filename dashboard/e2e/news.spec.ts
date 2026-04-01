import { test, expect } from '@playwright/test';

test.describe('News & AI page', () => {
  test('loads layout and headings', async ({ page }) => {
    await page.goto('/news');
    await expect(page.getByRole('heading', { name: /News & AI Analysis/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /AI Analysis \(Claude\)/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Economic Calendar/i })).toBeVisible();
  });

  test('Market intel column fits viewport (no horizontal scroll in main)', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/news');
    const main = page.locator('main');
    await expect(page.getByRole('heading', { name: /Market intel/i })).toBeVisible();
    const scrollW = await main.evaluate((el) => el.scrollWidth);
    const clientW = await main.evaluate((el) => el.clientWidth);
    expect(scrollW, 'main should not overflow horizontally').toBeLessThanOrEqual(clientW + 2);
  });
});
