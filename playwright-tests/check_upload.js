const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Enter PIN and navigate to Upload
  console.log('Logging in and going to Upload...');
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

  // Navigate to Upload
  await page.click('a[href="/upload"]');
  await page.waitForTimeout(3000);

  // Check the upload UI structure
  const uploadUI = await page.evaluate(() => {
    // Look for clickable elements
    const clickables = Array.from(document.querySelectorAll('button, label, [role="button"]')).map(el => ({
      tag: el.tagName,
      text: el.textContent?.substring(0, 50),
      class: el.className,
    }));

    // Look for the drop zone
    const dropzone = Array.from(document.querySelectorAll('div[class*="drop"], div[class*="upload"]')).map(d => ({
      class: d.className,
      text: d.textContent?.substring(0, 80),
    }));

    // Check file input
    const fileInput = document.querySelector('input[type="file"]');
    const parent = fileInput?.parentElement;

    return {
      clickables,
      dropzone,
      fileInput: fileInput ? {
        class: fileInput.className,
        hidden: fileInput.hidden,
        parent: parent ? {
          class: parent.className,
          tag: parent.tagName,
        } : null,
      } : null,
    };
  });
  console.log('Upload UI:', JSON.stringify(uploadUI, null, 2));

  // Try the correct interaction pattern
  console.log('\n=== Testing file upload interaction ===');

  // The input is hidden but we can interact with it directly
  const fileInput = page.locator('input[type="file"]');
  const isVisible = await fileInput.isVisible();
  console.log('File input visible():', isVisible);

  // Check if it's hidden via CSS
  const isHidden = await fileInput.isHidden();
  console.log('File input hidden():', isHidden);

  // We can still use setInputFiles even on hidden inputs
  // But first let's check what the page expects

  await browser.close();
  console.log('\n=== DONE ===');
})();
