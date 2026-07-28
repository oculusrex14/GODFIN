/**
 * Navigation helper that preserves authentication.
 * Use this instead of page.goto() for in-app navigation.
 */
async function navigateTo(page, path) {
  // For root path, just wait
  if (path === '/' || path === '') {
    await page.waitForTimeout(2000);
    return;
  }

  // For other paths, use click navigation to preserve auth
  const link = page.locator(`a[href="${path}"]`);
  const count = await link.count();

  if (count > 0) {
    await link.first().click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
  } else {
    // Fallback to goto if link not found
    console.warn(`Link for ${path} not found, falling back to goto`);
    await page.goto(path);
  }
}

module.exports = { navigateTo };
