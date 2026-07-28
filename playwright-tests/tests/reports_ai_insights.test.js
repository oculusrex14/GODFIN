const { test, expect } = require('@playwright/test');

test.use({
  baseURL: 'http://localhost:5200',
});

test('reports page loads with AI insights section', async ({ page }) => {
  // Navigate to PIN screen and authenticate
  await page.goto('/pin');

  // Fill 4-digit PIN (each digit goes into a separate input)
  const inputs = page.locator('input[type="password"]');
  await inputs.nth(0).fill('1');
  await inputs.nth(1).fill('2');
  await inputs.nth(2).fill('3');
  await inputs.nth(3).fill('4');

  // Wait for navigation to dashboard
  await page.waitForURL('/', { timeout: 10000 });

  // Navigate to Reports
  await page.click('text=Reports');
  await page.waitForURL('/reports', { timeout: 10000 });

  // Verify AI Insights section is visible
  await expect(page.locator('text=AI Financial Insights')).toBeVisible();

  // Verify Export section with CSV button
  await expect(page.locator('text=Export Reports')).toBeVisible();
  await expect(page.locator('text=Export CSV')).toBeVisible();
});
