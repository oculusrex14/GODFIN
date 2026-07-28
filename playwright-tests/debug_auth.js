const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Debug console
  page.on('console', msg => console.log('BROWSER LOG:', msg.text()));
  page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));

  // Enter PIN
  console.log('Loading app...');
  await page.goto('http://localhost:5200');
  await page.waitForLoadState('networkidle');

  // Wait for PIN inputs
  console.log('Waiting for PIN inputs...');
  const pinInputs = page.locator('input[type="password"]');
  await pinInputs.first().waitFor({ state: 'visible', timeout: 10000 });

  const count = await pinInputs.count();
  console.log(`Found ${count} PIN inputs`);

  // Enter PIN digits one by one with fill instead of typing
  const pin = '1234';
  for (let i = 0; i < 4; i++) {
    const input = pinInputs.nth(i);
    await input.click();
    await input.fill(pin[i]);
    console.log(`Entered digit ${i+1}: ${pin[i]}`);
    await page.waitForTimeout(200);
  }

  // Wait for form submission - check for any button click or form submit
  console.log('Waiting for auth to complete...');
  await page.waitForTimeout(3000);

  // Check localStorage for auth token
  const authToken = await page.evaluate(() => localStorage.getItem('auth_token'));
  console.log('Auth token in localStorage:', authToken ? 'present' : 'not found');

  // Wait more
  await page.waitForTimeout(2000);

  console.log('Current URL:', page.url());

  // Check if still on PIN screen
  const stillOnPin = await page.locator('text=Enter Your PIN').isVisible();
  console.log('Still on PIN screen:', stillOnPin);

  // Take screenshot
  await page.screenshot({ path: 'screenshots/after_pin.png', fullPage: true });

  await browser.close();
  console.log('\n=== DONE ===');
})();
