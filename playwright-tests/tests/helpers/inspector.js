const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Enter PIN manually
  console.log('Loading app and entering PIN...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  // Wait for PIN input fields to appear
  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 5000 });

  const count = await pinInputs.count();
  console.log(`Found ${count} PIN inputs`);

  if (count >= 4) {
    const pin = '1234';
    for (let i = 0; i < 4; i++) {
      const input = pinInputs.nth(i);
      await input.click();
      await input.fill(pin[i]);
      await page.waitForTimeout(100);
    }
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
  }

  console.log('URL after PIN entry:', page.url());

  // ---- FIND ALL INPUTS ON DASHBOARD ----
  const allInputs = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'));
    return inputs.map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
      id: i.id,
    }));
  });
  console.log('\nALL INPUTS ON DASHBOARD:', JSON.stringify(allInputs, null, 2));

  // ---- LOOK FOR SEARCH ----
  const searchLike = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    return all.filter(el => {
      const text = (el.textContent || '').toLowerCase();
      const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
      return text.includes('search') || placeholder.includes('search');
    }).map(el => ({
      tag: el.tagName,
      className: el.className,
      text: el.textContent.substring(0, 50),
    }));
  });
  console.log('\nSEARCH-LIKE ELEMENTS:', JSON.stringify(searchLike, null, 2));

  // Take screenshot
  await page.screenshot({ path: '../screenshots/inspector_home.png', fullPage: true });

  // ---- NAVIGATE TO TRANSACTIONS ----
  console.log('\n--- Navigating to Transactions ---');
  await page.goto('http://localhost:5200/transactions');
  await page.waitForTimeout(1500);
  await page.waitForLoadState('networkidle');

  const txInputs = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'));
    return inputs.map(i => ({
      type: i.type,
      placeholder: i.placeholder,
      className: i.className,
      id: i.id,
    }));
  });
  console.log('TRANSACTIONS PAGE INPUTS:', JSON.stringify(txInputs, null, 2));

  // Look for any search element on transactions
  const txSearch = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    return all.filter(el => {
      const text = (el.textContent || '').toLowerCase();
      const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
      return text.includes('search') || placeholder.includes('search');
    }).map(el => ({
      tag: el.tagName,
      className: el.className,
      text: el.textContent.substring(0, 50),
    }));
  });
  console.log('SEARCH ELEMENTS ON TRANSACTIONS:', JSON.stringify(txSearch, null, 2));

  await page.screenshot({ path: '../screenshots/inspector_transactions.png', fullPage: true });

  // ---- NAVIGATE TO UPLOAD ----
  console.log('\n--- Navigating to Upload ---');
  await page.goto('http://localhost:5200/upload');
  await page.waitForTimeout(1500);

  // Find file upload elements
  const uploadElements = await page.evaluate(() => {
    const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
    const labels = Array.from(document.querySelectorAll('label'));
    const buttons = Array.from(document.querySelectorAll('button'));
    return {
      fileInputs: fileInputs.map(i => ({
        type: i.type,
        className: i.className,
        id: i.id,
        accept: i.accept,
      })),
      labels: labels.filter(l => (l.textContent || '').toLowerCase().includes('upload')).map(l => ({
        tag: l.tagName,
        className: l.className,
        text: l.textContent.substring(0, 50),
      })),
      buttons: buttons.filter(b => (b.textContent || '').toLowerCase().includes('upload')).map(b => ({
        tag: b.tagName,
        className: b.className,
        text: b.textContent.substring(0, 50),
      })),
    };
  });
  console.log('UPLOAD ELEMENTS:', JSON.stringify(uploadElements, null, 2));

  await page.screenshot({ path: '../screenshots/inspector_upload.png', fullPage: true });

  // ---- NAVIGATE TO SETTINGS ----
  console.log('\n--- Navigating to Settings ---');
  await page.goto('http://localhost:5200/settings');
  await page.waitForTimeout(1500);

  const settingsText = await page.evaluate(() => document.body.innerText);
  console.log('SETTINGS PAGE (first 1500 chars):\n', settingsText.substring(0, 1500));

  // Look for Gmail in settings
  const gmailElements = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    return all.filter(el => {
      const text = (el.textContent || '').toLowerCase();
      return text.includes('gmail') || text.includes('email') || text.includes('google');
    }).map(el => ({
      tag: el.tagName,
      className: el.className,
      text: el.textContent.substring(0, 80),
    }));
  });
  console.log('\nGMAIL-RELATED ELEMENTS:', JSON.stringify(gmailElements, null, 2));

  await page.screenshot({ path: '../screenshots/inspector_settings.png', fullPage: true });

  // ---- CHECK NAV STRUCTURE ----
  console.log('\n--- Checking Nav ---');
  const navCheck = await page.evaluate(() => {
    const nav = document.querySelector('nav');
    const sidebar = document.querySelector('[class*="sidebar"], [class*="side"]');
    const links = document.querySelectorAll('a[href]');
    return {
      navFound: !!nav,
      sidebarFound: !!sidebar,
      linkCount: links.length,
      links: Array.from(links).slice(0, 10).map(a => ({
        href: a.href,
        text: a.textContent.substring(0, 30),
      })),
    };
  });
  console.log('NAV STRUCTURE:', JSON.stringify(navCheck, null, 2));

  await browser.close();
  console.log('\n=== INSPECTION COMPLETE ===');
})();
