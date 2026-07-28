const path = require('node:path');
const { test, expect } = require('@playwright/test');

test.describe.configure({ mode: 'serial' });

test('login → upload → classify → generate report', async ({ page }) => {
  const statementPath = process.env.GODFIN_E2E_STATEMENT;
  if (!statementPath) throw new Error('GODFIN_E2E_STATEMENT is required');

  const browserErrors = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });

  await page.goto('/pin');
  const pinInputs = page.locator('input[type="password"]');
  await expect(pinInputs).toHaveCount(4);
  for (const [index, digit] of [...'2468'].entries()) {
    await pinInputs.nth(index).fill(digit);
  }
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

  const pdfResult = await page.evaluate(async () => {
    const token = localStorage.getItem('godfin_auth_token');
    const response = await fetch('/api/v1/reports/pdf/summary?month=2026-07', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    return {
      ok: response.ok,
      status: response.status,
      prefix: String.fromCharCode(...bytes.slice(0, 4)),
      length: bytes.length,
    };
  });
  expect(pdfResult).toMatchObject({ ok: true, status: 200, prefix: '%PDF' });
  expect(pdfResult.length).toBeGreaterThan(1_000);

  await page.getByRole('link', { name: 'Cash Flow' }).click();
  await expect(page.getByRole('heading', { name: 'Cash-flow Calendar' })).toBeVisible();
  expect(browserErrors).toEqual([]);
});
