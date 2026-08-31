const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function expectNoSeriousAxeViolations(page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  const violations = result.violations.filter(
    (item) => item.impact === 'critical' || item.impact === 'serious',
  );
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

test('homepage presents an honest beta path and accessible media', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') pageErrors.push(message.text());
  });

  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'See your month. Keep the statement on your laptop.' }),
  ).toBeVisible();
  for (const link of ['Try the demo', 'How it works', 'Planned prices', 'Join the early testers']) {
    await expect(page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: link })).toBeVisible();
  }
  await expect(page.getByRole('link', { name: 'Tester sign in' })).toBeVisible();
  await expect(page.getByText('Actual GODFIN desktop interface · synthetic data · not connected to a bank')).toBeVisible();
  await expect(page.getByAltText(/real GODFIN desktop dashboard/i)).toBeVisible();
  const support = page.getByLabel('Current beta focus');
  await expect(support.getByText('Mac with Apple chip', { exact: true })).toBeVisible();
  await expect(support.getByText('Windows PC', { exact: true })).toBeVisible();

  const video = page.getByLabel('Silent GODFIN product walkthrough using one made-up household');
  await video.scrollIntoViewIfNeeded();
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute('poster', '/video/godfin-beta-hero.poster.webp');
  await expect(video.locator('source[type="video/webm"]')).toHaveAttribute('src', '/video/godfin-beta-hero.webm');
  await expect(video.locator('source[type="video/mp4"]')).toHaveAttribute('src', '/video/godfin-beta-hero.mp4');
  await expect(video.locator('track[kind="captions"]')).toHaveCount(1);
  expect(await video.evaluate((element) => element.muted)).toBe(true);
  await expect(page.getByText('Read the 24-second video transcript')).toBeVisible();

  await expect(page.locator('input[name="country"]')).toHaveCount(0);
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Computer')).toBeVisible();
  await expect(page.getByLabel('What do you want to understand?')).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('reduced motion keeps a poster and user-controlled playback', async ({ browser, baseURL }) => {
  const context = await browser.newContext({
    reducedMotion: 'reduce',
    viewport: { width: 1180, height: 800 },
  });
  const page = await context.newPage();
  await page.goto(`${baseURL}/`);
  const video = page.getByLabel('Silent GODFIN product walkthrough using one made-up household');
  await video.scrollIntoViewIfNeeded();
  await expect(video).toBeVisible();
  await expect(video).not.toHaveAttribute('autoplay', '');
  await expect(video).toHaveAttribute('controls', '');
  await expect(video).toHaveAttribute('poster', '/video/godfin-beta-hero.poster.webp');
  expect(await video.evaluate((element) => element.paused)).toBe(true);
  await context.close();
});

test('public demo uses the exact desktop interface and makes no finance-service requests', async ({ page }) => {
  const forbiddenRequests = [];
  page.on('request', (request) => {
    if (/\/api\/v1\/|supabase|cashfree|accounts\.google|gmail/i.test(request.url())) {
      forbiddenRequests.push(request.url());
    }
  });

  await page.goto('/demo');
  await expect(page).toHaveURL(/\/demo-app\/index\.html$/);
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  await expect(page.getByText('Synthetic desktop demo')).toBeVisible();
  await expect(page.getByText('Made-up household · no bank, Gmail, AI, or payment connection')).toBeVisible();

  for (const link of [
    'Dashboard', 'Transactions', 'Transfers', 'Review', 'Upload',
    'Budget', 'Subscriptions', 'Income', 'Reports', 'Cash Flow',
    'Net Worth', 'Behavior Insights', 'Advisor', 'Audit', 'Settings',
  ]) {
    await expect(page.getByRole('link', { name: link, exact: true })).toBeVisible();
  }

  await page.getByRole('link', { name: 'Transactions', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Transactions', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: /^SYNTHETIC SALARY\(Salary\)$/ })).toBeVisible();
  await page.getByRole('link', { name: 'Upload', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Upload Statement', exact: true })).toBeVisible();
  expect(await page.locator('input[type="file"]').count()).toBeGreaterThan(0);
  expect(forbiddenRequests).toEqual([]);
});

test('public demo and mobile navigation fit a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 760 });
  await page.goto('/demo');
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Activity', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open navigation menu' })).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
});

test('uninvited download and setup help both lead to the early testers', async ({ page }) => {
  await page.goto('/download');
  await expect(page.getByRole('heading', { name: 'Sign in with your invited email' })).toBeVisible();
  await expect(page.locator('.account-card').getByRole('link', { name: 'Join the early testers →' })).toBeVisible();

  await page.goto('/docs');
  await expect(page.getByRole('heading', { name: 'How to set up GODFIN on your computer' })).toBeVisible();
  await expect(page.locator('.content-card').getByRole('link', { name: 'Join the early testers' })).toBeVisible();
});

test('how-it-works states current support and non-goals plainly', async ({ page }) => {
  await page.goto('/how-it-works');
  await expect(page.getByRole('heading', { name: 'A monthly routine without the spreadsheet maze.' })).toBeVisible();
  for (const heading of [
    'Preview the statement',
    'Review the month',
    'Notice what repeats',
    'Move a goal forward',
    'Read the report',
  ]) {
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
  }
  await expect(page.getByText(/Intel Mac and Linux distribution remain later work/)).toBeVisible();
  await expect(page.getByText(/do not replace a CA or file a return/)).toBeVisible();
});

test('pricing is planned, lifetime-only, and has no public checkout', async ({ page }) => {
  await page.goto('/pricing');
  await expect(page.getByRole('heading', { name: 'Software you can own, not another monthly bill.' })).toBeVisible();
  await expect(page.getByText('₹4,999', { exact: true })).toBeVisible();
  await expect(page.getByText('₹9,999', { exact: true })).toBeVisible();
  await expect(page.getByText(/public checkout is closed/i)).toBeVisible();
  await expect(page.getByText('No bundled AI usage')).toBeVisible();
  await expect(page.getByRole('button', { name: /buy|purchase|checkout/i })).toHaveCount(0);
  await expect(page.getByText(/INR 1|₹1|purchasing power|PPP/i)).toHaveCount(0);
});

test('representative public pages have no serious accessibility violations', async ({ page }) => {
  for (const route of ['/', '/demo', '/how-it-works', '/pricing']) {
    await page.goto(route);
    await expectNoSeriousAxeViolations(page);
  }
});
