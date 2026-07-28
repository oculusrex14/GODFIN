const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Enter PIN
  console.log('Loading app...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  // Wait for PIN inputs
  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 10000 });

  // Enter PIN digits
  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    await pinInputs.nth(i).fill(pin[i]);
    await page.waitForTimeout(200);
  }

  // Wait longer for full auth + app render
  console.log('Waiting for auth and app load...');
  await page.waitForTimeout(5000);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  console.log('Current URL:', page.url());
  console.log('Page title:', await page.title());

  // Get full page text
  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log('\n=== BODY TEXT ===');
  console.log(bodyText.substring(0, 2000));

  // Check all elements
  const allElements = await page.evaluate(() => {
    return {
      divs: document.querySelectorAll('div').length,
      spans: document.querySelectorAll('span').length,
      buttons: document.querySelectorAll('button').length,
      links: document.querySelectorAll('a').length,
      inputs: document.querySelectorAll('input').length,
    };
  });
  console.log('\n=== ELEMENT COUNTS ===');
  console.log(JSON.stringify(allElements, null, 2));

  // Check if we can find any clickable nav elements
  const navElements = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('a, button')).slice(0, 15).map(el => ({
      tag: el.tagName,
      text: el.textContent?.substring(0, 30),
      href: el.href,
    }));
  });
  console.log('\n=== NAV/ELEMENT CANDIDATES ===');
  console.log(JSON.stringify(navElements, null, 2));

  await page.screenshot({ path: 'screenshots/debug_dashboard.png', fullPage: true });

  // Try navigating using click
  console.log('\n=== Trying to click nav link ===');
  const dashboardLink = page.locator('a[href*="dashboard"], a:has-text("Dashboard"), a:has-text("Transactions"), nav a').first();
  const linkCount = await dashboardLink.count();
  console.log(`Found ${linkCount} potential nav links`);

  if (linkCount > 0) {
    await dashboardLink.first().click();
    await page.waitForTimeout(2000);
    console.log('After click URL:', page.url());
  }

  await browser.close();
})();
