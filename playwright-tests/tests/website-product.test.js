const { test, expect } = require('@playwright/test');

test('homepage product chapters use real shipped feature demonstrations', async ({
  page,
}) => {
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.goto('/');

  await expect(
    page.getByRole('heading', {
      name: 'Follow the work, from statement to reviewed evidence.',
    }),
  ).toBeVisible();
  for (const heading of [
    'Review the bank file before it becomes your ledger.',
    'Correct it once. See why it was classified next time.',
    'A savings goal with a history—not a mystery number.',
    'Recurring does not mean guessed.',
    'Hand over evidence, warnings, and filing context together.',
    'Your finance database stays on your computer.',
  ]) {
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
  }

  const images = page.locator('#product-tour img');
  await expect(images).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    await images.nth(index).scrollIntoViewIfNeeded();
    await expect(images.nth(index)).toHaveJSProperty('complete', true);
  }
  const imageHealth = await images.evaluateAll((items) =>
    items.map((image) => ({
      complete: image.complete,
      naturalWidth: image.naturalWidth,
      alt: image.getAttribute('alt'),
    })),
  );
  expect(
    imageHealth.every(
      ({ complete, naturalWidth, alt }) =>
        complete && naturalWidth > 400 && Boolean(alt),
    ),
  ).toBe(true);

  const video = page.locator('#product-tour video');
  await expect(video).toHaveCount(1);
  expect(await video.evaluate((element) => element.muted)).toBe(true);
  await expect(video.locator('source[type="video/webm"]')).toHaveCount(1);
  await expect(video.locator('source[type="video/mp4"]')).toHaveCount(1);
  expect(pageErrors).toEqual([]);
});

test('reduced motion replaces autoplay with a real app still', async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    reducedMotion: 'reduce',
    viewport: { width: 1180, height: 800 },
  });
  const page = await context.newPage();
  await page.goto(`${baseURL}/`);
  await expect(page.locator('#product-tour video')).toHaveCount(0);
  await expect(
    page.getByAltText(
      'GODFIN statement import screen using privacy-safe synthetic data',
    ),
  ).toBeVisible();
  await context.close();
});

test('product tour fits a narrow viewport without horizontal overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 760 });
  await page.goto('/#product-tour');
  await expect(
    page.getByRole('heading', {
      name: 'Follow the work, from statement to reviewed evidence.',
    }),
  ).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
});

test('pricing remains lifetime-only with no bundled hosted AI credits', async ({
  page,
}) => {
  await page.goto('/pricing');
  await expect(page.getByText(/lifetime desktop licenses/i)).toBeVisible();
  await expect(
    page.getByText(/zero recurring hosted AI credits/i).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/per month|\/month|monthly allowance/i),
  ).toHaveCount(0);
});
