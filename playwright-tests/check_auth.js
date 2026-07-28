const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Loading app...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  console.log('Waiting for PIN inputs...');
  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 10000 });

  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    await pinInputs.nth(i).fill(pin[i]);
    await page.waitForTimeout(200);
  }

  console.log('Waiting for auth...');
  await page.waitForTimeout(5000);

  console.log('Current URL:', page.url());

  // Check all storage
  const storage = await page.evaluate(() => {
    return {
      localStorage: { ...localStorage },
      sessionStorage: { ...sessionStorage },
    };
  });
  console.log('LocalStorage:', JSON.stringify(storage.localStorage));
  console.log('SessionStorage:', JSON.stringify(storage.sessionStorage));

  // Check cookies
  const cookies = await context.cookies();
  console.log('Cookies:', JSON.stringify(cookies));

  // Check page content
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
  console.log('Page content:', bodyText);

  await page.screenshot({ path: 'screenshots/auth_check.png', fullPage: true });

  await browser.close();
})();
