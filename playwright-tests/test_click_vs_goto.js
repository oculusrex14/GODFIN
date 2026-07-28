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

  console.log('After click login, URL:', page.url());
  const text = await page.evaluate(() => document.body.innerText);
  console.log('Page text (first 500):', text.substring(0, 500));

  // Now click to go to transactions
  console.log('\nClicking on Transactions...');
  await page.click('a[href="/transactions"]');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  console.log('After click, URL:', page.url());
  const txText = await page.evaluate(() => document.body.innerText);
  console.log('Transactions text (first 500):', txText.substring(0, 500));

  // Now try refresh
  console.log('\nReloading...');
  await page.reload();
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  console.log('After reload, URL:', page.url());
  const reloadText = await page.evaluate(() => document.body.innerText);
  console.log('After reload (first 500):', reloadText.substring(0, 500));

  await browser.close();
})();
