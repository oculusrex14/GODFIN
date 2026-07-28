/**
 * Navigation Tests - Route Testing
 * Based on: system_map.md - Frontend Routes
 * Tests every page/route for proper loading without errors
 */

const { test, expect } = require('@playwright/test');
const { enterPIN, navigateTo } = require('./helpers/auth');

test.describe('Navigation Tests', () => {

  // Routes from system_map.md
  const routes = [
    { path: '/', name: 'Dashboard', titleCheck: 'GODFIN' },
    { path: '/transactions', name: 'Transactions', titleCheck: /transaction/i },
    { path: '/review', name: 'Review Queue', titleCheck: /review/i },
    { path: '/upload', name: 'Upload', titleCheck: /upload|statement/i },
    { path: '/budget', name: 'Budget', titleCheck: /budget|goal/i },
    { path: '/income', name: 'Income', titleCheck: /income/i },
    { path: '/reports', name: 'Reports', titleCheck: /report/i },
    { path: '/audit', name: 'Audit Manager', titleCheck: /audit/i },
    { path: '/settings', name: 'Settings', titleCheck: /setting/i },
  ];

  for (const route of routes) {
    test(`Route ${route.path} (${route.name}) loads correctly`, async ({ page }) => {
      await enterPIN(page);
      await page.goto(route.path);
      await page.waitForLoadState('networkidle');

      // Assert no redirect to error pages
      await expect(page).not.toHaveURL(/error|404|500/);

      // Assert page has content (not blank)
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.trim().length).toBeGreaterThan(10);

      // Assert no console errors
      const consoleErrors = [];
      page.on('console', msg => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });
      await page.waitForTimeout(500); // Wait for any console messages

      // Filter out expected React dev warnings
      const realErrors = consoleErrors.filter(err =>
        !err.includes('React DevTools') &&
        !err.includes('Warning:') &&
        !err.includes('development build')
      );
      expect(realErrors).toHaveLength(0);

      // Take screenshot for verification
      const routeName = route.path.replace('/', 'root').replace('/', '_') || 'root';
      await page.screenshot({ path: `../screenshots/route_${routeName}.png` });
    });
  }

  test('PIN route redirects authenticated user', async ({ page }) => {
    await enterPIN(page);
    await navigateTo(page, '/pin');
    await page.waitForLoadState('networkidle');

    // After PIN entry, /pin should redirect to /
    // Or show PIN screen again if PIN not verified
    const url = page.url();
    // Either we're on root (redirected) or still on PIN (need to enter again)
    expect(url).toMatch(/localhost:5200(\/|\/pin)?$/);
  });

  test('Protected route redirects unauthenticated user to PIN', async ({ page }) => {
    // Don't enter PIN - go directly to protected route
    await navigateTo(page, '/transactions');
    await page.waitForLoadState('networkidle');

    // Should be redirected to PIN screen or stay on PIN screen
    const url = page.url();
    expect(url).toContain('/pin');
  });

  test('Navigation menu contains all routes', async ({ page }) => {
    await enterPIN(page);
    await navigateTo(page, '/');
    await page.waitForLoadState('networkidle');

    // Check navigation links exist
    const nav = page.locator('nav');
    await expect(nav).toBeVisible();

    // Verify all main routes have navigation
    const navLinks = ['Transactions', 'Review', 'Upload', 'Budget', 'Income', 'Reports', 'Audit', 'Settings'];
    for (const link of navLinks) {
      const linkElement = page.locator(`nav a:has-text("${link}"), nav button:has-text("${link}")`);
      // At least one element with this text should exist
      const count = await linkElement.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test('Navigation between pages preserves session', async ({ page }) => {
    await enterPIN(page);

    // Navigate through multiple pages
    await navigateTo(page, '/transactions');
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL('/pin');

    await navigateTo(page, '/budget');
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL('/pin');

    await navigateTo(page, '/settings');
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL('/pin');

    // Session should persist
    await navigateTo(page, '/');
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL('/pin');
  });

  test('Page refresh maintains authentication', async ({ page }) => {
    await enterPIN(page);
    await navigateTo(page, '/transactions');
    await page.waitForLoadState('networkidle');

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Should still be on transactions, not redirected to PIN
    await expect(page).not.toHaveURL('/pin');
  });

  test('Direct URL access to protected routes requires authentication', async ({ page, context }) => {
    // Clear any existing auth
    await context.clearCookies();

    // Try to access protected route directly
    await navigateTo(page, '/settings');
    await page.waitForLoadState('networkidle');

    // Should redirect to PIN
    const url = page.url();
    expect(url).toContain('/pin');
  });
});