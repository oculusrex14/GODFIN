const fs = require('node:fs');
const path = require('node:path');
const { test, expect } = require('@playwright/test');

test.describe.configure({ mode: 'serial' });

const performanceBudgets = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, '../../performance/budgets.json'), 'utf8'),
);

function effectivePerformanceLimit(name) {
  const budget = performanceBudgets.budgets[name];
  return Math.min(
    budget.absolute_max,
    budget.accepted_baseline * (1 + performanceBudgets.regression_margin),
  );
}

async function measureNavigationPaint(page, target) {
  const duration = await page.evaluate(({ link, heading }) => new Promise((resolve, reject) => {
    const targetLink = [...document.querySelectorAll('a')]
      .find(element => element.textContent?.trim() === link);
    if (!targetLink) {
      reject(new Error(`Navigation link "${link}" was not found.`));
      return;
    }

    const started = performance.now();
    const deadline = started + 5_000;

    const waitForPaint = () => {
      const targetHeading = [...document.querySelectorAll('h1, h2, h3')]
        .find(element => (
          element.textContent?.trim() === heading
          && element.getClientRects().length > 0
        ));
      if (targetHeading) {
        requestAnimationFrame(() => resolve(performance.now() - started));
        return;
      }
      if (performance.now() >= deadline) {
        reject(new Error(`Heading "${heading}" was not painted within 5 seconds.`));
        return;
      }
      requestAnimationFrame(waitForPaint);
    };

    targetLink.click();
    requestAnimationFrame(waitForPaint);
  }), target);

  await expect(
    page.getByRole('heading', { name: target.heading, exact: true }),
  ).toBeVisible();
  return duration;
}

test('login → upload → classify → generate report', async ({ page }) => {
  const statementPath = process.env.GODFIN_E2E_STATEMENT;
  if (!statementPath) throw new Error('GODFIN_E2E_STATEMENT is required');

  const browserErrors = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.goto('/pin');
  const pinInput = page.getByLabel('Choose a 4 to 6 digit PIN');
  await pinInput.fill('2468');
  await page.getByRole('button', { name: 'Set PIN' }).click();
  await expect(page.getByRole('heading', { name: 'Make GODFIN yours' })).toBeVisible();
  await page.getByRole('button', { name: 'Finish setup later' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  await page.getByRole('link', { name: 'Upload' }).click();
  await expect(page.getByRole('heading', { name: 'Upload Statement' })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles(path.resolve(statementPath));
  await page.getByRole('button', { name: 'Upload & Reconcile' }).click();
  await expect(page.getByText('Reconciliation Review')).toBeVisible({ timeout: 15_000 });

  const importButton = page.getByRole('button', { name: /Import \d+ New Transactions/ });
  await expect(importButton).toBeEnabled();
  await importButton.click();
  await expect(page.getByText('Import Complete')).toBeVisible({ timeout: 15_000 });

  await page.getByRole('link', { name: 'Review' }).click();
  const reviewCard = page.getByRole('button', { name: /Review transaction: SYNTHETIC UNKNOWN MERCHANT/i });
  await expect(reviewCard).toBeVisible();
  await reviewCard.click();
  await page.getByRole('button', { name: 'SHOPPING', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm Classification' }).click();
  await expect(reviewCard).toHaveCount(0);

  await page.getByRole('link', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: 'Reports', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Export Reports' })).toBeVisible();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Summary PDF' }).click();
  const pdfDownload = await downloadPromise;
  const pdfStream = await pdfDownload.createReadStream();
  const pdfChunks = [];
  for await (const chunk of pdfStream) pdfChunks.push(chunk);
  const pdfBytes = Buffer.concat(pdfChunks);
  expect(pdfDownload.suggestedFilename()).toMatch(/^godfin_summary_.*\.pdf$/);
  expect(pdfBytes.subarray(0, 4).toString('ascii')).toBe('%PDF');
  expect(pdfBytes.length).toBeGreaterThan(1_000);

  await page.getByRole('link', { name: 'Cash Flow' }).click();
  await expect(page.getByRole('heading', { name: 'Cash-flow Calendar' })).toBeVisible();
  expect(browserErrors).toEqual([]);
});

test('common navigation stays within the accepted p95 budget', async ({ page }) => {
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('2468');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  const targets = [
    { link: 'Transactions', heading: 'Transactions' },
    { link: 'Upload', heading: 'Upload Statement' },
    { link: 'Reports', heading: 'Reports' },
    { link: 'Cash Flow', heading: 'Cash-flow Calendar' },
    { link: 'Settings', heading: 'Settings' },
  ];

  // Warm lazy-loaded chunks once; measurements represent common navigation
  // after the app has reached its normal interactive state.
  for (const target of targets) {
    await page.getByRole('link', { name: target.link, exact: true }).click();
    await expect(
      page.getByRole('heading', { name: target.heading, exact: true }),
    ).toBeVisible();
  }

  const measurements = [];
  for (let iteration = 0; iteration < 4; iteration += 1) {
    for (const target of targets) {
      measurements.push(await measureNavigationPaint(page, target));
    }
  }

  console.log(`Navigation paint samples: ${measurements.map(
    (duration, index) => `${targets[index % targets.length].link}=${duration.toFixed(1)}ms`,
  ).join(', ')}`);
  measurements.sort((left, right) => left - right);
  const p95 = measurements[Math.ceil(measurements.length * 0.95) - 1];
  expect(
    p95,
    `navigation p95 ${p95.toFixed(1)} ms exceeded accepted limit`,
  ).toBeLessThanOrEqual(effectivePerformanceLimit('navigation_p95_ms'));
});
