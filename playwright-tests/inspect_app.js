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
  await pinInputs.first().waitFor({ state: 'visible', timeout: 5000 });

  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    await pinInputs.nth(i).fill(pin[i]);
    await page.waitForTimeout(100);
  }

  // Wait for navigation
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  console.log('URL after login:', page.url());

  // Dashboard inputs
  const dashboardInputs = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('input')).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
      id: i.id,
    }));
  });
  console.log('\n=== DASHBOARD INPUTS ===');
  console.log(JSON.stringify(dashboardInputs, null, 2));

  await page.screenshot({ path: 'screenshots/dashboard.png', fullPage: true });

  // Transactions page
  console.log('\n=== TRANSACTIONS PAGE ===');
  await page.goto('http://localhost:5200/transactions');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  const txInputs = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('input')).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
      id: i.id,
    }));
  });
  console.log(JSON.stringify(txInputs, null, 2));

  // Search for any search elements
  const searchElements = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('*')).filter(el => {
      const text = el.textContent?.toLowerCase() || '';
      const placeholder = el.getAttribute('placeholder')?.toLowerCase() || '';
      return text.includes('search') || placeholder.includes('search');
    }).map(el => ({
      tag: el.tagName,
      class: el.className,
      text: el.textContent?.substring(0, 50),
    }));
  });
  console.log('\nSearch elements:', JSON.stringify(searchElements, null, 2));

  await page.screenshot({ path: 'screenshots/transactions.png', fullPage: true });

  // Upload page
  console.log('\n=== UPLOAD PAGE ===');
  await page.goto('http://localhost:5200/upload');
  await page.waitForTimeout(3000);

  const uploadInfo = await page.evaluate(() => {
    return {
      inputs: Array.from(document.querySelectorAll('input')).map(i => ({
        type: i.type,
        className: i.className,
      })),
      buttons: Array.from(document.querySelectorAll('button')).map(b => ({
        text: b.textContent?.substring(0, 30),
        className: b.className,
      })),
    };
  });
  console.log(JSON.stringify(uploadInfo, null, 2));

  await page.screenshot({ path: 'screenshots/upload.png', fullPage: true });

  // Settings page
  console.log('\n=== SETTINGS PAGE ===');
  await page.goto('http://localhost:5200/settings');
  await page.waitForTimeout(3000);

  const settingsText = await page.evaluate(() => document.body.innerText);
  console.log(settingsText.substring(0, 1500));

  await page.screenshot({ path: 'screenshots/settings.png', fullPage: true });

  await browser.close();
  console.log('\n=== DONE ===');
})();
