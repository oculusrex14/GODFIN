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
    page.getByRole('heading', { name: 'Your money, clearer. Your records, closer.' }),
  ).toBeVisible();
  for (const link of ['Demo', 'How it works', 'Pricing', 'Join beta']) {
    await expect(page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: link })).toBeVisible();
  }
  await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByText('Demo data - made-up household - nothing here is connected to a bank').first()).toBeVisible();
  const support = page.getByLabel('Current beta focus');
  await expect(support.getByText('Apple Silicon Mac', { exact: true })).toBeVisible();
  await expect(support.getByText('Windows x64', { exact: true })).toBeVisible();

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

test('public demo is auth-free, static, keyboard-operable, and makes no finance-service requests', async ({ page }) => {
  const forbiddenRequests = [];
  page.on('request', (request) => {
    if (/\/api\/|supabase|cashfree|accounts\.google|gmail/i.test(request.url())) {
      forbiddenRequests.push(request.url());
    }
  });

  await page.goto('/demo');
  await expect(page.getByRole('heading', { name: 'Try GODFIN with a household that does not exist.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start 2-minute tour' })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByText('Demo data - made-up household - nothing here is connected to a bank')).toBeVisible();

  await page.getByRole('button', { name: 'Start 2-minute tour' }).click();
  await expect(page.getByText('Step 1 of 6')).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByText('Step 2 of 6')).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByText('Step 1 of 6')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByText('Step 1 of 6')).toBeHidden();

  await page.getByRole('tab', { name: 'Transactions' }).click();
  const search = page.getByPlaceholder('Search this made-up month');
  await search.fill('salary');
  await expect(page.getByText('SYNTHETIC SALARY')).toBeVisible();
  await expect(page.getByText('SYNTHETIC GREEN BASKET')).toHaveCount(0);
  await page.getByRole('button', { name: 'Why?' }).click();
  await expect(page.getByText(/Verified income in the imported statement/)).toBeVisible();
  expect(forbiddenRequests).toEqual([]);
});

test('public demo and mobile navigation fit a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 760 });
  await page.goto('/demo');
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible();
  await page.getByRole('button', { name: 'Explore freely' }).click();
  await expect(page.getByRole('tab', { name: 'Overview' })).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
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
