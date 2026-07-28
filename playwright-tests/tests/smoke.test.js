const { test, expect } = require('@playwright/test');
const { enterPIN, isOnPinScreen } = require('./helpers/auth');

test.describe('Smoke Tests — App Startup', () => {

  test('App loads on port 5200', async ({ page }) => {
    const response = await page.goto('http://localhost:5200');
    expect(response.status()).toBeLessThan(400);
  });

  test('Backend responds on port 5100', async ({ page }) => {
    const response = await page.goto('http://localhost:5100');
    // FastAPI returns something (even a 404 on root is fine)
    expect(response).not.toBeNull();
  });

  test('PIN screen appears and accepts 1234', async ({ page }) => {
    await enterPIN(page);
    // After PIN entry, we should no longer be on the PIN screen
    const stillOnPinScreen = await isOnPinScreen(page);
    expect(stillOnPinScreen).toBe(false);

    // URL should not contain /pin anymore
    const url = page.url();
    console.log('URL after PIN entry:', url);
    expect(url).not.toContain('/pin');
  });

  test('Main app content visible after PIN', async ({ page }) => {
    await enterPIN(page);
    await page.screenshot({ path: '../screenshots/main_app.png' });

    // Verify the page has meaningful content (not blank or error)
    const hasContent = await page.locator('body').evaluate(el => {
      return el.innerText.trim().length > 0 &&
             !el.innerText.includes('Cannot GET') &&
             !el.innerText.includes('404');
    });
    expect(hasContent).toBe(true);

    // Verify we're past the PIN screen
    const stillOnPinScreen = await isOnPinScreen(page);
    expect(stillOnPinScreen).toBe(false);
  });

});