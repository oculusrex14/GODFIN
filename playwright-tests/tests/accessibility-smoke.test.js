const { test, expect } = require('@playwright/test');

test.use({
  viewport: { width: 390, height: 844 },
  hasTouch: true,
  isMobile: true,
});

test('PIN and beginner tutorial support keyboard, touch, and accessible names', async ({ page }) => {
  await page.goto('/pin');
  const pinInput = page.locator('input[type="password"]');
  await expect(pinInput).toHaveCount(1);
  await expect(pinInput).toHaveAttribute('aria-describedby', 'pin-length-hint');
  await expect(page.locator('#pin-length-hint')).toBeVisible();

  const submit = page.getByRole('button', { name: /Set PIN|Unlock/ });
  const inputBox = await pinInput.boundingBox();
  const buttonBox = await submit.boundingBox();
  expect(inputBox.height).toBeGreaterThanOrEqual(44);
  expect(buttonBox.height).toBeGreaterThanOrEqual(44);

  await expect(pinInput).toBeFocused();
  await pinInput.fill('2468');
  await page.keyboard.press('Tab');
  await expect(submit).toBeFocused();
  await page.keyboard.press('Enter');

  const onboardingHeading = page.getByRole('heading', { name: 'Make GODFIN yours' });
  const dashboardHeading = page.getByRole('heading', { name: 'Dashboard' });
  await expect(onboardingHeading.or(dashboardHeading)).toBeVisible();
  if (await onboardingHeading.isVisible()) {
    await page.getByRole('button', { name: 'Finish setup later' }).click();
  }
  await expect(dashboardHeading).toBeVisible();

  await page.getByRole('button', { name: 'Open navigation menu' }).click();
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  const learningSection = page.getByRole('button', { name: 'Setup & Learning' });
  await expect(learningSection).toHaveAttribute('aria-expanded', 'false');
  await learningSection.click();
  await expect(learningSection).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('button', { name: 'Learn GODFIN' }).click();
  await expect(
    page.getByRole('heading', { name: 'Finance basics, one calm step at a time' }),
  ).toBeVisible();

  await expect(page.getByLabel('Lesson 1 of 10')).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByLabel('Lesson 2 of 10')).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByLabel('Lesson 1 of 10')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});
