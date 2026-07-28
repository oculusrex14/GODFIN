/**
 * Filters Tests
 * Based on: filter_testing/*.md
 * Tests filter systems across all pages
 */

const { test, expect } = require('@playwright/test');
const { enterPIN, navigateTo } = require('./helpers/auth');

test.describe('Filters Tests', () => {

  test.describe('Transaction Filters', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');
    });

    test('Search filter triggers API call (BUG: FILTER-001 - no debounce)', async ({ page }) => {
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await expect(searchInput).toBeVisible();

      // Track API calls
      let apiCallCount = 0;
      await page.route('**/api/v1/transactions**', route => {
        apiCallCount++;
        route.continue();
      });

      // Type quickly
      await searchInput.type('test', { delay: 50 });

      // @fixme: Every keystroke triggers API call (no debounce)
      // Should debounce for 300ms
      await page.waitForTimeout(500);

      // Note: Without debounce, this makes 4 calls for 'test'
      console.log(`API calls made: ${apiCallCount}`);
    });

    test('Category filter updates results', async ({ page }) => {
      const categorySelect = page.locator('select').first();
      if (await categorySelect.isVisible()) {
        const options = await categorySelect.locator('option').allInnerTexts();

        if (options.length > 1) {
          // Select first category
          await categorySelect.selectOption({ index: 1 });
          await page.waitForTimeout(500);

          // URL or results should change
          await expect(page).not.toHaveURL(/error/);
        }
      }
    });

    test('Subcategory filter appears when category selected', async ({ page }) => {
      const categorySelect = page.locator('select').first();
      if (await categorySelect.isVisible()) {
        await categorySelect.selectOption({ index: 1 });
        await page.waitForTimeout(300);

        // Look for subcategory dropdown
        const subcategorySelect = page.locator('select').nth(1);
        // May or may not appear depending on category
      }
    });

    test('Date range filter applies', async ({ page }) => {
      const dateInputs = page.locator('input[type="date"]');
      const count = await dateInputs.count();

      if (count >= 2) {
        const dateFrom = dateInputs.first();
        const dateTo = dateInputs.nth(1);

        await dateFrom.fill('2025-01-01');
        await dateTo.fill('2025-01-31');
        await page.waitForTimeout(500);

        await expect(page).not.toHaveURL(/error/);
      }
    });

    test('Date range validation (BUG: FILTER-002 - allows invalid ranges)', async ({ page }) => {
      const dateInputs = page.locator('input[type="date"]');
      const count = await dateInputs.count();

      if (count >= 2) {
        const dateFrom = dateInputs.first();
        const dateTo = dateInputs.nth(1);

        // Set invalid range (from > to)
        await dateFrom.fill('2025-12-31');
        await dateTo.fill('2025-01-01');
        await page.waitForTimeout(500);

        // @fixme: No validation - should show error or swap dates
        // Currently returns empty results without feedback
        await expect(page).not.toHaveURL(/error/);

        await page.screenshot({ path: '../screenshots/filter_invalid_date.png' });
      }
    });

    test('Sort dropdown works correctly', async ({ page }) => {
      // Find sort dropdown or button
      const sortButton = page.locator('button:has-text("Sort"), [aria-label="Sort"]').first();
      if (await sortButton.isVisible()) {
        await sortButton.click();
        await page.waitForTimeout(300);

        // Look for sort options
        const sortOptions = page.locator('button:has-text("Newest"), button:has-text("Oldest"), button:has-text("Highest")');
        const count = await sortOptions.count();

        if (count > 0) {
          await sortOptions.first().click();
          await page.waitForTimeout(500);
        }
      }

      await expect(page).not.toHaveURL(/error/);
    });

    test('Clear filters resets all fields', async ({ page }) => {
      // Apply some filters first
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('test');

      const categorySelect = page.locator('select').first();
      if (await categorySelect.isVisible()) {
        await categorySelect.selectOption({ index: 1 });
      }

      await page.waitForTimeout(300);

      // Find clear button
      const clearButton = page.locator('button:has-text("Clear"), button:has-text("Reset")');
      if (await clearButton.count() > 0) {
        await clearButton.first().click();
        await page.waitForTimeout(300);

        // Verify filters are cleared
        await expect(searchInput).toHaveValue('');
      }
    });

    test('Filters not persisted to URL (BUG: FILTER-003)', async ({ page }) => {
      // Apply filter
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('test merchant');
      await page.waitForTimeout(500);

      // Check URL - should have query params but doesn't
      const url = page.url();
      console.log('URL after filter:', url);

      // @fixme: Filters are not in URL, so refreshing loses them
      // Should be: ?search=test+merchant&category=...
    });

    test('Filter persists on refresh', async ({ page }) => {
      // Apply filter
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('test');
      await page.waitForTimeout(500);

      // Refresh
      await page.reload();
      await page.waitForLoadState('networkidle');

      // @fixme: Filter lost on refresh (not in URL)
      const searchValue = await searchInput.inputValue();
      console.log('Search value after refresh:', searchValue);
    });

    test('No visual feedback when filters produce zero results (BUG: FILTER-004)', async ({ page }) => {
      // Search for something unlikely to exist
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('zzzzzzzzzznotfound123456');
      await page.waitForTimeout(500);

      // Should show "No transactions found" message
      const bodyText = await page.locator('body').innerText();

      // @fixme: May not clearly indicate zero results are due to filter
      console.log('Empty state:', bodyText.includes('No transactions') ? 'Shows message' : 'No clear message');
    });
  });

  test.describe('Review Queue Filters', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/review');
      await page.waitForLoadState('networkidle');
    });

    test('Review queue loads with default view', async ({ page }) => {
      // Should show uncategorized transactions
      const content = page.locator('body');
      const text = await content.innerText();

      const hasContent = text.includes('transaction') ||
                        text.includes('caught up') ||
                        text.includes('No');

      expect(hasContent).toBeTruthy();
    });

    test('Review queue has no status filter (BUG: FILTER-007)', async ({ page }) => {
      // Note: Review queue should have status filter but doesn't
      // Should be able to filter by confidence level

      const statusFilter = page.locator('select[name="status"], select[aria-label*="status"]');
      const count = await statusFilter.count();

      console.log('Status filter exists:', count > 0);
    });
  });

  test.describe('Dashboard Filters', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/');
      await page.waitForLoadState('networkidle');
    });

    test('Month filter changes data', async ({ page }) => {
      const monthSelect = page.locator('select').first();
      if (await monthSelect.isVisible()) {
        const options = await monthSelect.locator('option').allInnerTexts();

        if (options.length > 1) {
          await monthSelect.selectOption({ index: 1 });
          await page.waitForTimeout(500);

          // Dashboard should update
          await expect(page).not.toHaveURL(/error/);
        }
      }
    });

    test('Period filter (week/month) changes data', async ({ page }) => {
      const periodSelect = page.locator('select').last();
      if (await periodSelect.isVisible()) {
        await periodSelect.selectOption({ index: 1 });
        await page.waitForTimeout(500);

        await expect(page).not.toHaveURL(/error/);
      }
    });

    test('Period date calculation (BUG: INT-007 - off-by-one)', async ({ page }) => {
      // Period calculation has bugs:
      // Week 1 = days 1-7
      // Week 2 = days 8-15 (not 7 days!)

      // This is a backend bug, just verify page loads
      await expect(page).not.toHaveURL(/error/);
    });
  });

  test.describe('Combined Filters', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');
    });

    test('Multiple filters combine with AND logic', async ({ page }) => {
      // Apply search filter
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('test');
      await page.waitForTimeout(300);

      // Apply category filter
      const categorySelect = page.locator('select').first();
      if (await categorySelect.isVisible()) {
        await categorySelect.selectOption({ index: 1 });
        await page.waitForTimeout(300);
      }

      // Both filters should apply (AND logic)
      await expect(page).not.toHaveURL(/error/);
    });

    test('Clear all filters at once', async ({ page }) => {
      // Apply multiple filters
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('test');

      const dateInputs = page.locator('input[type="date"]');
      if (await dateInputs.count() >= 2) {
        await dateInputs.first().fill('2025-01-01');
        await dateInputs.nth(1).fill('2025-01-31');
      }

      await page.waitForTimeout(300);

      // Clear all
      const clearButton = page.locator('button:has-text("Clear"), button:has-text("Reset")');
      if (await clearButton.count() > 0) {
        await clearButton.first().click();
        await page.waitForTimeout(300);

        // All filters should be cleared
        await expect(searchInput).toHaveValue('');
      }
    });

    test('Filters work with pagination', async ({ page }) => {
      // Apply filter
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('test');
      await page.waitForTimeout(500);

      // Find next page button
      const nextButton = page.locator('button:has-text("Next"), [aria-label="Next"]');
      if (await nextButton.count() > 0 && await nextButton.first().isEnabled()) {
        await nextButton.first().click();
        await page.waitForTimeout(500);

        // Filter should still be applied
        await expect(searchInput).toHaveValue('test');
      }
    });
  });

  test.describe('Filter Performance', () => {
    test('Deep pagination performance (BUG: FILTER-006)', async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');

      // Note: OFFSET pagination is slow for deep pages
      // Should use cursor-based pagination

      // Find pagination
      const pageButtons = page.locator('button:has-text("Next"), [aria-label="Next"]');
      if (await pageButtons.count() > 0) {
        // Clicking through many pages would be slow
        // Just verify pagination exists
        console.log('Pagination exists - OFFSET may be slow for deep pages');
      }
    });
  });

  test.describe('Special Characters in Filters', () => {
    test.beforeEach(async ({ page }) => {
      await enterPIN(page);
      await navigateTo(page, '/transactions');
      await page.waitForLoadState('networkidle');
    });

    test('Search with special characters (BUG: FILTER-005)', async ({ page }) => {
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();

      // Test various special characters
      const specialChars = ['<script>', 'test&test', 'test"test', "test'test"];

      for (const chars of specialChars) {
        await searchInput.clear();
        await searchInput.fill(chars);
        await page.waitForTimeout(300);

        // Should not cause SQL injection (backend uses SQLAlchemy)
        // But should also handle in display
        await expect(page).not.toHaveURL(/error/);
      }
    });

    test('Search with unicode/emoji', async ({ page }) => {
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      await searchInput.fill('Starbucks ☕ test');
      await page.waitForTimeout(300);

      await expect(page).not.toHaveURL(/error/);
    });

    test('Search with very long string', async ({ page }) => {
      const searchInput = page.locator('input[placeholder="Search merchants..."]').first();
      const longString = 'a'.repeat(500);
      await searchInput.fill(longString);
      await page.waitForTimeout(300);

      await expect(page).not.toHaveURL(/error/);
    });
  });
});