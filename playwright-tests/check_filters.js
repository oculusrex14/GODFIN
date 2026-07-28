const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Enter PIN and navigate to Transactions
  console.log('Logging in and going to Transactions...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 10000 });

  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    await pinInputs.nth(i).fill(pin[i]);
    await page.waitForTimeout(200);
  }
  await page.waitForTimeout(5000);
  await page.waitForLoadState('networkidle');

  // Click on Transactions
  await page.click('a[href="/transactions"]');
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle');

  // Check for the All Categories dropdown/button
  console.log('=== FILTER UI ===');
  const filterUI = await page.evaluate(() => {
    // Find elements that look like filters
    const buttons = Array.from(document.querySelectorAll('button'));
    const categoryFilter = buttons.find(b => b.textContent?.includes('All Categories'));
    const sortFilter = buttons.find(b => b.textContent?.includes('Newest First') || b.textContent?.includes('Sort'));

    return {
      categoryFilter: categoryFilter ? {
        text: categoryFilter.textContent,
        class: categoryFilter.className,
      } : null,
      sortFilter: sortFilter ? {
        text: sortFilter.textContent,
        class: sortFilter.className,
      } : null,
    };
  });
  console.log(JSON.stringify(filterUI, null, 2));

  // Click on All Categories to see the dropdown
  console.log('\nClicking All Categories...');
  const categoryBtn = page.locator('button:has-text("All Categories")');
  if (await categoryBtn.isVisible()) {
    await categoryBtn.click();
    await page.waitForTimeout(1000);

    const dropdownContent = await page.evaluate(() => {
      const dropdowns = document.querySelectorAll('[class*="dropdown"], [class*="menu"], [class*="select"], [class*="popover"]');
      return Array.from(dropdowns).map(d => ({
        class: d.className,
        text: d.textContent?.substring(0, 200),
      }));
    });
    console.log('Dropdown content:', JSON.stringify(dropdownContent, null, 2));

    await page.screenshot({ path: 'screenshots/categories_open.png', fullPage: true });
  }

  // Check for empty state - navigate to Review page
  console.log('\n=== REVIEW PAGE EMPTY STATE ===');
  await page.click('a[href="/review"]');
  await page.waitForTimeout(3000);

  const reviewText = await page.evaluate(() => document.body.innerText);
  console.log(reviewText.substring(0, 1500));

  // Check for "all clear" or empty messages
  const emptyState = await page.evaluate(() => {
    const all = document.querySelectorAll('*');
    return Array.from(all).filter(el => {
      const text = el.textContent?.toLowerCase() || '';
      return text.includes('all clear') || text.includes('no transaction') || text.includes('empty') || text.includes('no pending');
    }).map(el => ({
      tag: el.tagName,
      class: el.className,
      text: el.textContent?.substring(0, 80),
    }));
  });
  console.log('\nEmpty state elements:', JSON.stringify(emptyState, null, 2));

  await page.screenshot({ path: 'screenshots/review.png', fullPage: true });

  await browser.close();
  console.log('\n=== DONE ===');
})();
