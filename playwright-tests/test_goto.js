const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Enter PIN
  console.log('Logging in...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 10000 });

  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    await pinInputs.nth(i).fill(pin[i]);
    await page.waitForTimeout(200);
  }

  // Wait for auth to complete
  await page.waitForTimeout(5000);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  console.log('URL after login:', page.url());

  // Check localStorage
  const storage = await page.evaluate(() => {
    return {
      localStorage: Object.keys(localStorage),
      localStorageValues: Object.entries(localStorage).reduce((acc, [k, v]) => {
        acc[k] = v.substring(0, 50);
        return acc;
      }, {}),
    };
  });
  console.log('Storage:', JSON.stringify(storage, null, 2));

  // Try using goto to same URL (refresh)
  console.log('\nRefreshing page...');
  await page.goto('http://localhost:5200/');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  console.log('URL after refresh:', page.url());
  const text = await page.evaluate(() => document.body.innerText);
  console.log('Page text (first 500):', text.substring(0, 500));

  // Try goto to different URL
  console.log('\nGoing to /transactions via goto...');
  await page.goto('http://localhost:5200/transactions');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  console.log('URL after goto transactions:', page.url());
  const txText = await page.evaluate(() => document.body.innerText);
  console.log('Transactions text (first 500):', txText.substring(0, 500));

  await browser.close();
})();
