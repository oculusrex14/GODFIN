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

async function mockAuthenticatedApp(page, licenseOverride = null) {
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
      '/onboarding': {
        completed: true,
        deferred: true,
        current_step: 10,
        tutorial_step: 1,
        tutorial_version: 1,
        tutorial_completed: false,
      },
      '/audit/sessions': [],
      '/review/stats': { queue_size: 0 },
      '/ingest/gmail/sync-status': { status: 'idle', percent: 0 },
      '/goals': [{
        id: 7,
        name: 'Emergency cushion',
        target_amount: 200000,
        current_saved: 45000,
        deadline_date: '2027-12-31',
        annual_return_rate: 0,
      }],
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
      '/settings/backups': [{
        filename: 'godfin-backup.db',
        size_bytes: 2097152,
        created_at: '2026-07-29T10:30:00Z',
      }],
      '/system/status': { status: 'ok' },
      '/system/embeddings/status': { status: 'not_installed' },
      '/system/local-ai/profile': {
        choice: 'local',
        total_ram_gb: 16,
        available_ram_gb: 10,
        disk_free_gb: 120,
        acceleration: 'apple_silicon',
        context_tokens: 8192,
        privacy: 'Prompts stay on this computer.',
        installer_url: 'https://ollama.com/download',
        ollama: { installed: false },
        recommendation: {
          label: 'Qwen 4B',
          reason: 'A comfortable fit for this computer.',
          model: 'qwen3:4b',
          size_gb: 2.5,
          memory_gb: 6,
          expected_speed: 'Responsive for short explanations',
        },
        recommendations: [],
      },
      '/system/local-ai/download': { status: 'idle' },
      '/accounts': [],
      '/accounts/parser-profiles': [],
      '/accounts/sender-mappings': [],
      '/auth/gmail/status': { connected: false },
      '/license': licenseOverride || {
        tier: 'free',
        valid: false,
        status: 'inactive',
        features: [],
        message: 'GODFIN Core is active.',
        topup_credits: 0,
      },
      '/llm/config': { is_active: false, configurations: [] },
      '/settings/classification-memory': {
        corrections: [],
        total_confirmed: 0,
        personal_classifier: { enabled: false, eligible: false },
      },
      '/reward-pilot/status': { consented: false, enabled: false },
      '/reports/summary': {
        total_income: 85000,
        total_spend: 57000,
        savings_rate: 0,
        recurring_total: 10500,
        financial_health_score: 72,
        financial_health_label: 'A steady month',
        financial_health_caveat: 'This money picture is based only on the activity recorded in GODFIN.',
        all_categories: [{ category: 'Food & Dining', amount: 12000 }],
      },
      '/reports/detailed': {
        category_comparison: [],
        income_breakdown: [{ source: 'Salary', amount: 85000 }],
        recurring_list: [{ merchant: 'Internet', amount: 1200 }],
        top_merchants: [],
      },
      '/behavior-insights': {
        policy: 'These observations stay on this computer and are never used to judge you.',
        monthly_budget: null,
        reflections: [{
          key: 'small-purchases',
          title: 'Small purchases are adding up',
          observation: 'You made 8 purchases under ₹500 this month.',
          question: 'Were these useful, or did some happen without much thought?',
          action: 'Try pausing for ten seconds before the next small purchase.',
          evidence: '8 recorded purchases',
          confidence: 'high',
        }],
        metrics: [{
          key: 'savings-consistency',
          label: 'How regularly you keep money aside',
          value: 68,
          unit: 'score',
          meaning: 'Shows whether saving happens in most months.',
          formula: 'Months with savings ÷ months reviewed',
          inputs: 'Recorded income and spending',
          period: 'Last 6 complete months',
          provenance: 'Calculated locally',
          caveat: 'Missing activity can change this result.',
          confidence: 'medium',
          difficulty: 'Easy',
          hidden: false,
          user_note: '',
        }],
      },
    };
    const exact = responses[path];
    if (exact !== undefined) return route.fulfill({ json: exact });
    if (path.startsWith('/audit/sessions?')) return route.fulfill({ json: [] });
    if (path.startsWith('/settings/classification-memory?')) {
      return route.fulfill({ json: responses['/settings/classification-memory'] });
    }
    if (path.startsWith('/goals/7/contributions')) {
      return route.fulfill({ json: [] });
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

test('paid CA export is one review-oriented ZIP tax pack', async ({ page }) => {
  await mockAuthenticatedApp(page, {
    tier: 'pro',
    valid: true,
    status: 'active',
    features: ['advanced_reports'],
    message: 'GODFIN Pro is active.',
    topup_credits: 0,
  });
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Reports', exact: true }).click();

  await expect(page.getByRole('button', { name: 'Download CA Tax Pack' })).toBeEnabled();
  await expect(page.getByText(/multi-sheet workbook, raw CSV, manifest/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'CA CSV' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'CA JSON' })).toHaveCount(0);
});

test('review fixes expose the new brand, safe settings controls, and resumable app tour', async ({ page }) => {
  await mockAuthenticatedApp(page);
  await page.goto('/pin');
  await expect(page.getByLabel('GODFIN')).toBeVisible();
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Settings', exact: true }).click();

  for (const section of [
    'Trust & Service Health',
    'Setup & Learning',
    'License & Plan',
    'Gmail Integration',
    'AI Model Configuration',
    'Backup & Export',
    'Data Management',
  ]) {
    await expect(page.getByRole('button', { name: section })).toHaveAttribute('aria-expanded', 'false');
  }

  await page.getByRole('button', { name: 'Backup & Export' }).click();
  await expect(page.getByText('29 Jul 2026, 4:00 pm')).toBeVisible();
  await expect(page.getByText(/2 MB.*godfin-backup\.db/)).toBeVisible();

  await page.getByRole('button', { name: 'AI Model Configuration' }).click();
  await page.getByRole('button', { name: 'Match similar transaction descriptions' }).click();
  await expect(page.getByText(/download about 100 MB/)).toBeVisible();
  await page.getByRole('button', { name: 'Not now' }).click();

  const ollamaPopup = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Open official Ollama installer' }).click();
  const popup = await ollamaPopup;
  await popup.waitForLoadState('domcontentloaded');
  expect(popup.url()).toMatch(/^https:\/\/ollama\.com\/download/);
  await popup.close();

  await page.getByRole('button', { name: 'Setup & Learning' }).click();
  await page.getByRole('button', { name: /app tour/i }).first().click();
  await expect(page.getByRole('complementary', { name: /GODFIN app tour/ })).toBeVisible();
  await expect(page.getByText('Your money at a glance')).toBeVisible();
  await page.getByRole('button', { name: 'Close and resume the tour later' }).click();
});

test('behavior reflections lead with plain language and deeper measures follow', async ({ page }) => {
  await mockAuthenticatedApp(page, {
    tier: 'max',
    valid: true,
    status: 'active',
    features: ['behavior_insights', 'advanced_reports'],
    message: 'GODFIN Max is active.',
    topup_credits: 0,
  });
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Behavior Insights', exact: true }).click();

  await expect(page.getByRole('heading', { name: 'Your Money Habits' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Things worth reflecting on' })).toBeVisible();
  await expect(page.getByText('Small purchases are adding up')).toBeVisible();
  await expect(page.getByText(/without much thought/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The numbers behind your habits' })).toBeVisible();
  await expect(page.getByText('How regularly you keep money aside')).toBeVisible();
});

test('reports require connected AI for commentary and goals show a direct savings action', async ({ page }) => {
  await mockAuthenticatedApp(page, {
    tier: 'max',
    valid: true,
    status: 'active',
    features: ['behavior_insights', 'advanced_reports'],
    message: 'GODFIN Max is active.',
    topup_credits: 0,
  });
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Reports', exact: true }).click();

  await expect(page.getByText('Your financial report', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('72/100')).toBeVisible();
  await expect(page.getByText(/Connect an AI to create the detailed written analysis/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Detailed AI PDF' })).toBeDisabled();

  await page.getByRole('link', { name: 'Budget', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Add savings' })).toBeVisible();
  await page.getByRole('button', { name: 'Add savings' }).click();
  await expect(page.getByRole('heading', { name: /Update Emergency cushion/ })).toBeVisible();
  await expect(page.getByLabel('Change')).toHaveValue('deposit');
});
