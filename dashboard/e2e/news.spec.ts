import { test, expect } from '@playwright/test';

test.describe('News & AI page', () => {
  test('loads layout and headings', async ({ page }) => {
    await page.goto('/news');
    await expect(page.getByRole('heading', { name: /News & AI Analysis/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /AI Analysis \(Claude\)/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Economic Calendar/i })).toBeVisible();
  });
});
