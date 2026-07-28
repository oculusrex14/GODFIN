/**
 * Enters the PIN 1234 on the app's PIN screen.
 * The PIN screen has 4 separate input fields, one for each digit.
 * Auto-submits when all 4 digits are entered.
 */
async function enterPIN(page) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Wait for PIN input fields to appear
  const pinInputs = page.locator('input[type="password"]');
  const count = await pinInputs.count();

  if (count < 4) {
    // Take a screenshot for debugging
    await page.screenshot({ path: '../screenshots/pin_screen_debug.png' });
    throw new Error(`Expected 4 PIN input fields, found ${count}. Check pin_screen_debug.png`);
  }

  // Enter each digit into its respective field
  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    const input = pinInputs.nth(i);
    await input.click();
    await input.fill(pin[i]);
    // Small delay to ensure the digit is registered
    await page.waitForTimeout(100);
  }

  // Wait for auto-submit (onComplete callback) and navigation
  await page.waitForTimeout(500);
  await page.waitForLoadState('networkidle');

  // Wait longer for auth to fully settle
  await page.waitForTimeout(3000);

  // Verify we're past the PIN screen by checking URL
  const currentUrl = page.url();
  console.log('URL after PIN entry:', currentUrl);

  // Take a screenshot for verification
  await page.screenshot({ path: '../screenshots/after_pin.png' });
}

/**
 * Check if currently on PIN screen
 */
async function isOnPinScreen(page) {
  const pinInputs = page.locator('input[type="password"]');
  const count = await pinInputs.count();
  return count >= 4;
}

/**
 * Navigate to a path preserving auth.
 * IMPORTANT: After enterPIN(), use this instead of page.goto()
 * because page.goto() causes re-authentication.
 */
async function navigateTo(page, path) {
  // Root path - just wait for app to be ready
  if (path === '/' || path === '') {
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    return;
  }

  // Try to find a link with the exact path
  let link = page.locator(`a[href="${path}"]`);

  // If not found, try with trailing slash
  if ((await link.count()) === 0 && !path.endsWith('/')) {
    link = page.locator(`a[href="${path}/"]`);
  }

  const count = await link.count();

  if (count > 0) {
    await link.first().click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
  } else {
    // Fallback to goto if link not found (will re-authenticate)
    console.warn(`Link for ${path} not found, using goto (may lose auth)`);
    await page.goto(path);
    await page.waitForTimeout(2000);
  }
}

module.exports = { enterPIN, isOnPinScreen, navigateTo };
