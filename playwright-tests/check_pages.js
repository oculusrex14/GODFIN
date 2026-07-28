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

  // Navigate to Transactions
  console.log('Navigating to Transactions...');
  await page.goto('http://localhost:5200/transactions');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  // Get full page content
  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log('\n=== TRANSACTIONS PAGE ===');
  console.log(bodyText.substring(0, 3000));

  // Get all inputs
  const inputs = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('input')).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
      id: i.id,
      name: i.name,
    }));
  });
  console.log('\n=== INPUTS ===');
  console.log(JSON.stringify(inputs, null, 2));

  // Get all elements that might be search
  const searchLike = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('*')).filter(el => {
      const text = el.textContent?.toLowerCase() || '';
      const placeholder = el.getAttribute('placeholder')?.toLowerCase() || '';
      const aria = el.getAttribute('aria-label')?.toLowerCase() || '';
      return text.includes('search') || placeholder.includes('search') || aria.includes('search');
    }).map(el => ({
      tag: el.tagName,
      class: el.className,
      text: el.textContent?.substring(0, 50),
    }));
  });
  console.log('\n=== SEARCH-LIKE ELEMENTS ===');
  console.log(JSON.stringify(searchLike, null, 2));

  // Get any filter inputs
  const filterInputs = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'));
    // Filter to likely filter/search inputs (not password or hidden)
    return inputs.filter(i => !['password', 'hidden', 'checkbox', 'radio'].includes(i.type)).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
    }));
  });
  console.log('\n=== FILTER INPUTS (non-password) ===');
  console.log(JSON.stringify(filterInputs, null, 2));

  await page.screenshot({ path: 'screenshots/transactions.png', fullPage: true });

  // Upload page
  console.log('\n\n=== UPLOAD PAGE ===');
  await page.goto('http://localhost:5200/upload');
  await page.waitForTimeout(3000);

  const uploadText = await page.evaluate(() => document.body.innerText);
  console.log(uploadText.substring(0, 1500));

  const uploadInputs = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('input')).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
    }));
  });
  console.log('\n=== UPLOAD INPUTS ===');
  console.log(JSON.stringify(uploadInputs, null, 2));

  await page.screenshot({ path: 'screenshots/upload.png', fullPage: true });

  // Settings page
  console.log('\n\n=== SETTINGS PAGE ===');
  await page.goto('http://localhost:5200/settings');
  await page.waitForTimeout(3000);

  const settingsText = await page.evaluate(() => document.body.innerText);
  console.log(settingsText.substring(0, 2000));

  await page.screenshot({ path: 'screenshots/settings.png', fullPage: true });

  await browser.close();
  console.log('\n=== DONE ===');
})();
