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

  console.log('After login URL:', page.url());

  // Navigate using CLICK instead of goto
  console.log('\nClicking on Transactions link...');
  await page.click('a[href="/transactions"]');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  console.log('After click URL:', page.url());
  const txBody = await page.evaluate(() => document.body.innerText);
  console.log('\n=== TRANSACTIONS PAGE (via click) ===');
  console.log(txBody.substring(0, 1500));

  // Get inputs
  const inputs = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('input')).map(i => ({
      type: i.type,
      placeholder: i.placeholder,
    }));
  });
  console.log('\nInputs:', JSON.stringify(inputs, null, 2));

  await page.screenshot({ path: 'screenshots/tx_click.png', fullPage: true });

  // Upload page via click
  console.log('\nClicking Upload link...');
  await page.click('a[href="/upload"]');
  await page.waitForTimeout(3000);

  console.log('URL after Upload:', page.url());
  const uploadBody = await page.evaluate(() => document.body.innerText);
  console.log('\n=== UPLOAD PAGE (via click) ===');
  console.log(uploadBody.substring(0, 1500));

  await page.screenshot({ path: 'screenshots/upload_click.png', fullPage: true });

  // Check for file input elements
  const fileElements = await page.evaluate(() => {
    return {
      fileInputs: Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
        type: i.type,
        class: i.className,
      })),
      allDivs: Array.from(document.querySelectorAll('div')).length,
      divsWithUpload: Array.from(document.querySelectorAll('div')).filter(d =>
        (d.className || '').toLowerCase().includes('upload')
      ).length,
    };
  });
  console.log('\nFile elements:', JSON.stringify(fileElements, null, 2));

  await browser.close();
  console.log('\n=== DONE ===');
})();
