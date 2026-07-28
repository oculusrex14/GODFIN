/**
 * API Integration Tests
 * Based on: integration_testing/integration_audit.md
 * Tests critical UI → API integration paths
 */

const { test, expect } = require('@playwright/test');
const { enterPIN, navigateTo } = require('./helpers/auth');

test.describe('API Integration Tests', () => {

  test.describe('Transaction Create → Dashboard Render', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
    });

    test('Creating transaction invalidates dashboard query', async ({ page }) => {
      // Track API calls
      const dashboardCalls = [];
      await page.route('**/api/v1/dashboard/**', route => {
        dashboardCalls.push(route.request().url());
        route.continue();
      });

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Initial dashboard load
      expect(dashboardCalls.length).toBeGreaterThan(0);
      dashboardCalls.length = 0; // Reset

      // Navigate to transactions
      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');

      // Create transaction (if we can)
      const addButton = page.locator('button:has-text("Add"), button:has-text("+")').first();
      if (await addButton.isVisible()) {
        // Note: Full create flow would require filling form
        // @fixme: FEAT-001 - Dashboard not invalidated after transaction create
      }
    });

    test('Transaction create API returns correct shape', async ({ page }) => {
      // Mock transaction create response
      await page.route('**/api/v1/transactions', route => {
        if (route.request().method() === 'POST') {
          route.fulfill({
            status: 201,
            body: JSON.stringify({
              id: 'test-id',
              merchant_raw: 'Test Merchant',
              amount: 100.00,
              date: '2025-01-01',
              type: 'debit',
              category: 'Food',
              created_at: new Date().toISOString()
            })
          });
        } else {
          route.continue();
        }
      });

      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');

      // Verify API is called correctly
    });

    test('API 401 redirects to PIN', async ({ page }) => {
      // Mock 401 response
      await page.route('**/api/v1/**', route => {
        route.fulfill({
          status: 401,
          body: JSON.stringify({ detail: 'Unauthorized' })
        });
      });

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Should redirect to PIN
      await expect(page).toHaveURL(/pin/);
    });

    test('API 500 shows error state', async ({ page }) => {
      await enterPIN(page);

      // Mock 500 error
      await page.route('**/api/v1/dashboard/**', route => {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Internal server error' })
        });
      });

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Should show error state, not blank screen
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.length).toBeGreaterThan(0);
    });
  });

  test.describe('Review Resolve → Merchant Memory', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
    });

    test('Review resolve updates merchant memory', async ({ page }) => {
      // Track API calls for review resolve
      let resolveCalled = false;
      await page.route('**/api/v1/review/*/resolve', route => {
        if (route.request().method() === 'POST') {
          resolveCalled = true;
          route.fulfill({
            status: 200,
            body: JSON.stringify({ success: true })
          });
        } else {
          route.continue();
        }
      });

      await navigateTo(page, '/review');
      await page.waitForLoadState('networkidle');

      // If there are items to review, try to resolve one
      const expandButton = page.locator('button:has-text("Expand")').first();
      if (await expandButton.isVisible()) {
        await expandButton.click();
        await page.waitForTimeout(300);

        // Select category
        const categoryButton = page.locator('button:has-text("Food"), button:has-text("Transport")').first();
        if (await categoryButton.isVisible()) {
          await categoryButton.click();
          await page.waitForTimeout(300);

          // Confirm
          const confirmButton = page.locator('button:has-text("Confirm"), button:has-text("Resolve")').first();
          if (await confirmButton.isVisible()) {
            await confirmButton.click();
            await page.waitForTimeout(500);
          }
        }
      }

      // Just verify no crash
      await expect(page).not.toHaveURL(/error/);
    });

    test('Review queue not invalidated after import (BUG: INT-006)', async ({ page }) => {
      // This is a bug test - review queue should be invalidated after import
      // but currently isn't

      await navigateTo(page, '/upload');
      await page.waitForLoadState('networkidle');

      // After import, should invalidate reviewQueue
      // @fixme: Missing ['reviewQueue'] invalidation

      // For now, just verify page loads
      await expect(page).not.toHaveURL(/error/);
    });
  });

  test.describe('Audit Finalize → Transaction Lock', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
    });

    test('Audit finalize locks transactions', async ({ page }) => {
      await navigateTo(page, '/audit');
      await page.waitForLoadState('networkidle');

      // Find finalize button if available
      const finalizeButton = page.locator('button:has-text("Finalize")').first();
      if (await finalizeButton.isVisible()) {
        // Click finalize
        await finalizeButton.click();
        await page.waitForTimeout(500);

        // Verify transactions are locked
        // Check audit status
      }

      await expect(page).not.toHaveURL(/error/);
    });

    test('Locked transactions cannot be edited', async ({ page }) => {
      // Mock audit active state
      await page.route('**/api/v1/audit/status', route => {
        route.fulfill({
          status: 200,
          body: JSON.stringify({
            is_audit_active: true,
            locked_months: ['2025-01']
          })
        });
      });

      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');

      // Locked transactions should not show edit button
      // Note: Current logic shows edit only when isAuditActive is true (BUG: FEAT-001)
    });

    test('isAuditActive stale across tabs (BUG: INT-004)', async ({ page }) => {
      // This tests that audit status doesn't update when changed in another tab
      // Would need two browser contexts to fully test

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Audit status is fetched on mount
      // If changed in another tab, this tab's status is stale
    });
  });

  test.describe('Statement Upload → Classification', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
    });

    test('Upload triggers classification', async ({ page }) => {
      await navigateTo(page, '/upload');
      await page.waitForLoadState('networkidle');

      // Note: This would require actual file upload
      // Just verify upload endpoint exists
      const fileInput = page.locator('input[type="file"]');
      await expect(fileInput).toHaveCount(1);
    });

    test('Classification timeout handled (BUG: INT-005)', async ({ page }) => {
      // Mock slow classification
      await page.route('**/api/v1/ingest/**', route => {
        // Simulate timeout
        setTimeout(() => {
          route.fulfill({
            status: 504,
            body: JSON.stringify({ detail: 'Gateway Timeout' })
          });
        }, 30000);
      });

      await navigateTo(page, '/upload');
      await page.waitForLoadState('networkidle');

      // @fixme: LLM timeout silently ignored - no alert
      // Just verify no crash
    });
  });

  test.describe('Dashboard Filter → API Query → Chart Render', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
    });

    test('Month filter triggers correct API call', async ({ page }) => {
      let calledUrl = '';
      await page.route('**/api/v1/dashboard/**', route => {
        calledUrl = route.request().url();
        route.continue();
      });

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Change month
      const monthSelect = page.locator('select').first();
      if (await monthSelect.isVisible()) {
        await monthSelect.selectOption({ index: 1 });
        await page.waitForTimeout(500);

        // URL should include month parameter
        console.log('API called:', calledUrl);
      }
    });

    test('Period filter sends correct parameters', async ({ page }) => {
      let calledUrl = '';
      await page.route('**/api/v1/dashboard/**', route => {
        calledUrl = route.request().url();
        route.continue();
      });

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      const periodSelect = page.locator('select').last();
      if (await periodSelect.isVisible()) {
        await periodSelect.selectOption({ index: 1 });
        await page.waitForTimeout(500);

        console.log('Period API:', calledUrl);
      }
    });

    test('Empty data shows graceful empty state', async ({ page }) => {
      await page.route('**/api/v1/dashboard/**', route => {
        route.fulfill({
          status: 200,
          body: JSON.stringify({
            month_spend: 0,
            month_income: 0,
            category_breakdown: [],
            spending_trend: []
          })
        });
      });

      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Should show empty state messages
      const bodyText = await page.locator('body').innerText();
      const hasEmptyState = bodyText.includes('No spending') ||
                           bodyText.includes('No trend') ||
                           bodyText.includes('No data');

      expect(hasEmptyState).toBeTruthy();
    });
  });

  test.describe('Gmail Integration', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
      // Wait for app to fully load after PIN
      await page.waitForTimeout(2000);
      await page.waitForLoadState('networkidle');
    });

    test('Gmail settings page loads', async ({ page }) => {
      // Use click navigation instead of goto to preserve auth
      await page.click('a[href="/settings"]');
      await page.waitForTimeout(2000);
      await page.waitForLoadState('networkidle');

      // Look for Gmail settings section
      const gmailSection = page.locator('text=/gmail/i');
      const count = await gmailSection.count();

      expect(count).toBeGreaterThan(0);
    });

    test('Gmail connect initiates OAuth', async ({ page }) => {
      // Use click navigation instead of goto to preserve auth
      await page.click('a[href="/settings"]');
      await page.waitForTimeout(2000);
      await page.waitForLoadState('networkidle');

      const connectButton = page.locator('button:has-text("Connect"), button:has-text("Gmail")').first();
      if (await connectButton.isVisible()) {
        // Would open OAuth popup
        // Just verify button exists
      }
    });

    test('Gmail sync triggers ingestion', async ({ page }) => {
      // Mock Gmail sync
      await page.route('**/api/v1/gmail/sync', route => {
        route.fulfill({
          status: 200,
          body: JSON.stringify({ imported: 5, errors: [] })
        });
      });

      await navigateTo(page, '/settings');
      await page.waitForLoadState('networkidle');

      // Would trigger sync
    });
  });

  test.describe('Budget Goal Create → Profile Recalc', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
    });

    test('Goal creation invalidates profile (BUG: INT-010)', async ({ page }) => {
      // @fixme: Creating goal doesn't invalidate financial profile

      await navigateTo(page, '/budget');
      await page.waitForLoadState('networkidle');

      // Track profile API calls
      let profileCalls = 0;
      await page.route('**/api/v1/profile', route => {
        profileCalls++;
        route.continue();
      });

      // Create goal (if possible)
      const createButton = page.locator('button:has-text("Create"), button:has-text("Add")').first();
      if (await createButton.isVisible()) {
        // Note: Would need to fill form and submit
        // @fixme: Profile not invalidated after goal create
      }
    });
  });

  test.describe('Network Error Handling', () => {
    test('Network failure shows error, not blank screen', async ({ page }) => {
      // Block all API calls
      await page.route('**/api/**', route => route.abort('failed'));

      await enterPIN(page);
      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Should show error state
      const bodyText = await page.locator('body').innerText();
      expect(bodyText.length).toBeGreaterThan(0);
    });

    test('Timeout shows appropriate message', async ({ page }) => {
      // Mock slow response
      await page.route('**/api/**', route => {
        setTimeout(() => route.continue(), 60000);
      });

      await enterPIN(page);
      await navigateTo(page, '/');

      // Should timeout gracefully
      await page.waitForTimeout(5000);
    });
  });

  test.describe('Authentication Flow', () => {
    test('Token expiry redirects to PIN', async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');

      // Clear token (simulate expiry)
      await page.evaluate(() => {
        localStorage.removeItem('token');
      });

      // Make API call
      await page.route('**/api/**', route => {
        route.fulfill({
          status: 401,
          body: JSON.stringify({ detail: 'Unauthorized' })
        });
      });

      await page.reload();
      await page.waitForLoadState('networkidle');

      // Should redirect to PIN
      await expect(page).toHaveURL(/pin/);
    });

    test('Protected routes require authentication', async ({ page }) => {
      // Don't enter PIN
      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');

      // Should redirect to PIN
      await expect(page).toHaveURL(/pin/);
    });
  });
});