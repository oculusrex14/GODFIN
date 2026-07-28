const { test, expect } = require('@playwright/test');

test('data reset flow with PIN and confirmation', async ({ page }) => {
  // 1. Login
  await page.goto('http://localhost:5200/pin');
  await page.waitForSelector('input[type="password"]', { timeout: 15000 });
  const inputs = await page.locator('input[type="password"]').all();
  for (let i = 0; i < 4; i++) await inputs[i].fill(String((i + 1) % 10));
  await page.waitForURL(/\/$/, { timeout: 15000 });

  // 2. Go to Settings
  await page.goto('http://localhost:5200/settings');
  await page.waitForLoadState('networkidle');

  // 3. Scroll to find and click "Reset Data" button
  const resetBtn = page.getByRole('button', { name: /Reset Data/i });
  await resetBtn.scrollIntoViewIfNeeded();
  await expect(resetBtn).toBeVisible({ timeout: 10000 });
  await resetBtn.click();

  // 4. Confirmation dialog should appear
  await expect(page.getByText(/Reset All Data\?/i)).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/permanently delete/)).toBeVisible();

  // 5. Click "Reset Everything" to confirm
  await page.getByRole('button', { name: /Reset Everything/i }).click();

  // 6. PIN prompt should appear
  await expect(page.getByText(/Enter PIN to Reset Data/)).toBeVisible({ timeout: 5000 });
  const pinInputs = await page.locator('input[type="password"]').all();
  expect(pinInputs.length).toBeGreaterThanOrEqual(4);
  for (let i = 0; i < 4; i++) await pinInputs[i].fill(String((i + 1) % 10));

  // 7. Wait for success toast
  await expect(page.getByText(/All data has been reset|Data reset/)).toBeVisible({ timeout: 15000 });

  // 8. Verify we're still on Settings
  await expect(page).toHaveURL(/settings/);
});
