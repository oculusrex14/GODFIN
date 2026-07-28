const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Enter PIN
  console.log('Loading app and logging in...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 10000 });

  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    await pinInputs.nth(i).fill(pin[i]);
    await page.waitForTimeout(200);
  }

  // Wait for app load
  await page.waitForTimeout(5000);
  await page.waitForLoadState('networkidle');

  // Settings page
  console.log('Clicking Settings...');
  await page.click('a[href="/settings"]');
  await page.waitForTimeout(3000);

  console.log('Settings URL:', page.url());
  const settingsBody = await page.evaluate(() => document.body.innerText);
  console.log('\n=== SETTINGS PAGE ===');
  console.log(settingsBody);

  // Look for Gmail elements
  const gmailElements = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('*')).filter(el => {
      const text = el.textContent?.toLowerCase() || '';
      return text.includes('gmail') || text.includes('google') || text.includes('email');
    }).map(el => ({
      tag: el.tagName,
      class: el.className,
      text: el.textContent?.substring(0, 80),
    }));
  });
  console.log('\n=== GMAIL ELEMENTS ===');
  console.log(JSON.stringify(gmailElements, null, 2));

  await page.screenshot({ path: 'screenshots/settings.png', fullPage: true });

  // Check empty states - go to Transactions and try filtering for something that won't exist
  console.log('\n=== CHECKING EMPTY STATES ===');

  // First add a filter that might return no results
  await page.click('a[href="/transactions"]');
  await page.waitForTimeout(2000);

  // Click on a category filter to see if there's an empty state
  const categoryButtons = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button, div[role="button"]')).map(el => ({
      tag: el.tagName,
      text: el.textContent?.substring(0, 30),
      class: el.className,
    }));
  });
  console.log('\n=== CATEGORY/ FILTER BUTTONS ===');
  console.log(JSON.stringify(categoryButtons.slice(0, 20), null, 2));

  // Check if there's a category dropdown/filter UI
  const filterElements = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('[class*="filter"], [class*="select"], [class*="dropdown"]')).map(el => ({
      class: el.className,
      text: el.textContent?.substring(0, 50),
    }));
  });
  console.log('\n=== FILTER ELEMENTS ===');
  console.log(JSON.stringify(filterElements, null, 2));

  await browser.close();
  console.log('\n=== DONE ===');
})();
