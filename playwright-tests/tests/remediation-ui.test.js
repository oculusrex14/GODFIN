const { test, expect } = require('@playwright/test');

const API_PREFIX = '/api/v1';

async function mockPinApi(page, authStatus, verifyResponse) {
  await page.route(`**${API_PREFIX}/**`, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.slice(API_PREFIX.length);
    if (path === '/health') {
      return route.fulfill({ json: { status: 'ok' } });
    }
    if (path === '/auth/status') {
      return route.fulfill({ json: authStatus });
    }
    if (path === '/auth/verify-pin') {
      return route.fulfill(verifyResponse);
    }
    return route.fulfill({ json: {} });
  });
}

async function mockAuthenticatedApp(page) {
  const profile = {
    savings_rate: 18.5,
    impulse_index: 22.1,
    fixed_expense_ratio: 41.2,
    recurring_burden: 12.8,
    subscription_dependency: 5.4,
    lifestyle_inflation: 3.2,
  };
  await page.route(`**${API_PREFIX}/**`, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.slice(API_PREFIX.length);
    const responses = {
      '/health': { status: 'ok' },
      '/auth/status': { is_first_run: false, pin_length: 4 },
      '/auth/verify-pin': { authenticated: true, token: 'test-token' },
      '/onboarding': { completed: true, deferred: true, current_step: 10 },
      '/audit/sessions': [],
      '/review/stats': { queue_size: 0 },
      '/ingest/gmail/sync-status': { status: 'idle', percent: 0 },
      '/goals': [],
      '/goal-contribution-suggestions': { enabled: false, items: [] },
      '/profile': profile,
      '/recurring': [],
      '/settings': { theme: 'dark', allow_network_access: 'false' },
      '/settings/health': {
        gmail: { status: 'not_configured' },
        llm: { status: 'not_configured' },
        backup: { status: 'healthy' },
      },
      '/settings/developer': { enabled: false, rules: [] },
      '/settings/backups': [],
      '/system/status': { status: 'ok' },
      '/system/embeddings/status': { status: 'not_installed' },
      '/system/local-ai/profile': { choice: 'none', recommendations: [] },
      '/system/local-ai/download': { status: 'idle' },
      '/accounts': [],
      '/accounts/parser-profiles': [],
      '/accounts/sender-mappings': [],
      '/auth/gmail/status': { connected: false },
      '/license': {
        tier: 'free',
        valid: false,
        status: 'inactive',
        features: [],
        message: 'GODFIN Core is active.',
        topup_credits: 0,
      },
      '/settings/classification-memory': {
        corrections: [],
        total_confirmed: 0,
        personal_classifier: { enabled: false, eligible: false },
      },
      '/reward-pilot/status': { consented: false, enabled: false },
      '/reports/summary': {
        income: 0,
        expenses: 0,
        savings: 0,
        savings_rate: 0,
      },
      '/reports/detailed': { categories: [], transactions: [] },
    };
    const exact = responses[path];
    if (exact !== undefined) return route.fulfill({ json: exact });
    if (path.startsWith('/audit/sessions?')) return route.fulfill({ json: [] });
    if (path.startsWith('/settings/classification-memory?')) {
      return route.fulfill({ json: responses['/settings/classification-memory'] });
    }
    if (path.startsWith('/reports/')) return route.fulfill({ json: {} });
    return route.fulfill({ json: {} });
  });
}

async function navigateFromMobileMenu(page, label) {
  await page.getByRole('button', { name: 'Open navigation menu' }).click();
  await page.getByRole('link', { name: label, exact: true }).click();
}

test('PIN boxes use the saved length and rate-limit countdown from the server', async ({ page }) => {
  await mockPinApi(
    page,
    { is_first_run: false, pin_length: 6 },
    {
      status: 429,
      headers: { 'Retry-After': '17', 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: 'Too many failed attempts.' }),
    },
  );

  await page.goto('/pin');
  const pinInput = page.getByLabel('Enter your PIN');
  const slots = page.locator('[data-pin-slots]');
  await expect(slots).toHaveAttribute('data-pin-slots', '6');
  await pinInput.fill('48265');
  await expect(page.getByRole('button', { name: 'Unlock' })).toBeDisabled();
  await pinInput.fill('482650');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await expect(page.getByText('Try again in 0:17')).toBeVisible();
});

test('unknown migrated PIN length expands on keyboard and paste input', async ({ page }) => {
  await mockPinApi(
    page,
    { is_first_run: false, pin_length: null },
    { json: { authenticated: true, token: 'test-token' } },
  );
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/pin');

  const pinInput = page.getByLabel('Enter your PIN');
  const slots = page.locator('[data-pin-slots]');
  await expect(slots).toHaveAttribute('data-pin-slots', '4');
  await pinInput.pressSequentially('48265');
  await expect(slots).toHaveAttribute('data-pin-slots', '5');

  await pinInput.fill('');
  await page.evaluate(() => navigator.clipboard.writeText('48265073'));
  await pinInput.press(process.platform === 'darwin' ? 'Meta+V' : 'Control+V');
  await expect(pinInput).toHaveValue('48265073');
  await expect(slots).toHaveAttribute('data-pin-slots', '8');
});

test('calculation help stays in the viewport and settings remember expansion', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await mockAuthenticatedApp(page);
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();

  await navigateFromMobileMenu(page, 'Budget');
  await expect(page.getByRole('heading', { name: 'Budget & Goals' })).toBeVisible();
  const infoButton = page.getByRole('button', { name: 'How Savings Rate is calculated' });
  await infoButton.hover();
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip).toBeVisible();
  const box = await tooltip.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(320);
  expect(box.y + box.height).toBeLessThanOrEqual(700);
  await page.keyboard.press('Escape');
  await expect(tooltip).toHaveCount(0);

  await navigateFromMobileMenu(page, 'Settings');
  const appSettings = page.getByRole('button', { name: 'App Settings' });
  await expect(appSettings).toHaveAttribute('aria-expanded', 'false');
  await appSettings.click();
  await expect(appSettings).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('theme', { exact: true })).toBeVisible();
  await navigateFromMobileMenu(page, 'Budget');
  await navigateFromMobileMenu(page, 'Settings');
  await expect(page.getByRole('button', { name: 'App Settings' })).toHaveAttribute('aria-expanded', 'true');
});

test('locked report insights link to current lifetime pricing', async ({ page }) => {
  await mockAuthenticatedApp(page);
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  const pricing = page.getByRole('link', { name: 'View license options' });
  await expect(pricing).toHaveAttribute('href', 'https://godfin.vercel.app/pricing');
  await expect(pricing).toHaveAttribute('target', '_blank');
});

test('goal creation explains opening savings and expected return', async ({ page }) => {
  await mockAuthenticatedApp(page);
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Budget', exact: true }).click();
  await page.getByRole('button', { name: 'New Goal' }).click();

  await expect(page.getByLabel('Already Saved (optional)')).toHaveValue('0');
  await expect(page.getByLabel('Expected Annual Return % (optional)')).toHaveValue('0');
  await page.getByLabel('Already Saved (optional)').fill('25000');
  await page.getByLabel('Expected Annual Return % (optional)').fill('6.5');
  await expect(page.getByLabel('Already Saved (optional)')).toHaveValue('25000');
  await expect(page.getByLabel('Expected Annual Return % (optional)')).toHaveValue('6.5');
});
