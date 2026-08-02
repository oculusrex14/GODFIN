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
        registry: {
          signature_verified: true,
          registry_version: '2026.08.01.1',
          source: 'bundled',
          error: null,
        },
        recommendation: {
          label: 'Qwen 4B',
          reason: 'A comfortable fit for this computer.',
          model: 'qwen3:4b',
          size_gb: 2.5,
          memory_gb: 6,
          expected_speed: 'Responsive for short explanations',
          expected_digest: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        },
        recommendations: [],
      },
      '/system/local-ai/download': { status: 'idle' },
      '/accounts': [],
      '/accounts/parser-profiles': [],
      '/accounts/sender-mappings': [],
      '/auth/gmail/status': {
        connected: false,
        status: 'not_configured',
        message: 'Gmail connection is not configured for this GODFIN build yet.',
        retryable: false,
        action_required: 'owner_configuration',
        digest_email_supported: false,
      },
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
        calculation_version: 'behavior-insights-v2.0',
        window_months: 6,
        period: '2026-01-01 through 2026-06-30',
        coverage: {
          observed_months: 6,
          included_transactions: 42,
          current_month_excluded: true,
          note: 'Only finished calendar months are considered. Missing imports can still change a result.',
        },
        policy: 'These observations stay on this computer and are never used to judge you.',
        monthly_budget: null,
        reflections: [{
          key: 'small-purchases',
          title: 'Small purchases are adding up',
          observation: 'You made 8 purchases under ₹500 this month.',
          question: 'Were these useful, or did some happen without much thought?',
          action: 'Try pausing for ten seconds before the next small purchase.',
          evidence: '8 recorded purchases',
          available: true,
          unavailable_reason: null,
          confidence: 'high',
        }],
        metrics: [
          {
            key: 'savings-consistency',
            label: 'How regularly you keep money aside',
            value: 68,
            unit: 'score',
            meaning: 'Shows whether saving happens in most months.',
            formula: 'Months with savings ÷ months reviewed',
            inputs: 'Recorded income and spending',
            period: '2026-01-01 through 2026-06-30',
            provenance: 'Calculated locally',
            caveat: 'Missing activity can change this result.',
            available: true,
            unavailable_reason: null,
            sample_size: 6,
            minimum_sample: 2,
            confidence: 'medium',
            difficulty: 'easy',
            hidden: false,
            user_note: '',
          },
          {
            key: 'routine-stability',
            label: 'How similar your active money days are each week',
            value: null,
            unit: 'score',
            meaning: 'Compares the number of days with money activity from week to week.',
            formula: 'Variation in active days across full weeks',
            inputs: 'Transaction dates',
            period: '2026-01-01 through 2026-06-30',
            provenance: 'Calculated locally',
            caveat: 'Missing activity can change this result.',
            available: false,
            unavailable_reason: 'At least 8 full calendar weeks with recorded activity are needed before showing a routine score.',
            sample_size: 1,
            minimum_sample: 8,
            confidence: 'insufficient',
            difficulty: 'advanced',
            hidden: false,
            user_note: '',
          },
        ],
      },
      '/subscriptions': [{
        id: 'usd-fixture',
        name: 'USD service',
        amount: 10,
        currency: 'USD',
        amount_inr: null,
        conversion_status: 'unavailable',
        conversion_as_of: null,
        conversion_provider: 'European Central Bank reference rates via Frankfurter',
        conversion_stale: null,
        conversion_unavailable_reason: 'Live currency rates are temporarily unavailable.',
        frequency: 'monthly',
        category: 'Software',
        subcategory: null,
        next_payment_date: null,
        is_active: true,
        notes: null,
        created_at: '2026-07-01T00:00:00',
      }],
      '/subscriptions/stats': {
        total_monthly_cost: null,
        total_annual_projection: null,
        active_count: 1,
        inactive_count: 0,
        by_category: null,
        exchange_rates: {},
        fx: {
          status: 'unavailable',
          provider: 'European Central Bank reference rates via Frankfurter',
          as_of: null,
          stale: null,
          unavailable_reason: 'Live currency rates are temporarily unavailable.',
        },
      },
      '/subscriptions/exchange-rates/refresh': {
        updated: 0,
        fx: {
          status: 'unavailable',
          provider: 'European Central Bank reference rates via Frankfurter',
          as_of: null,
          stale: null,
          unavailable_reason: 'Live currency rates are temporarily unavailable.',
        },
      },
      '/subscriptions/suggestions': [],
      '/subscriptions/reminders': { days: 7, reminders: [] },
      '/net-worth/market-data/config/status': {
        provider: 'Twelve Data',
        configured: false,
        base_currency: 'INR',
        supported_base_currencies: ['INR', 'USD', 'EUR', 'GBP'],
        key_storage: 'encrypted_local',
      },
      '/net-worth': {
        base_currency: 'INR',
        valuation_status: 'incomplete',
        total_assets: null,
        total_liabilities: null,
        net_worth: null,
        stale_count: 1,
        unavailable_item_count: 1,
        valued_item_count: 0,
        item_count: 1,
        calculation_version: 'net_worth_v2',
        provenance: 'Calculated locally from native values and verified rates.',
        items: [{
          id: 'usd-asset',
          name: 'USD cash reserve',
          item_type: 'asset',
          asset_class: 'cash',
          valuation_mode: 'manual',
          symbol: null,
          quantity: 1,
          currency: 'USD',
          manual_value: 100,
          native_value: 100,
          value_base: null,
          exchange_rate_to_base: null,
          base_currency: 'INR',
          source: 'Redacted test statement',
          valued_at: '2026-08-01',
          expires_on: '2026-09-01',
          stale: true,
          available: false,
          unavailable_reason: 'No recent verified USD to INR exchange rate is available.',
          provenance: 'manual',
          is_active: true,
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
  await page.getByRole('button', { name: 'Match similar transaction descriptions' }).dispatchEvent('click');
  await expect(page.getByText(/download about 100 MB/)).toBeVisible();
  await page.getByRole('button', { name: 'Not now' }).click();

  const ollamaPopup = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Open official Ollama installer' }).click();
  const popup = await ollamaPopup;
  await popup.waitForLoadState('domcontentloaded');
  expect(popup.url()).toMatch(/^https:\/\/ollama\.com\/download/);
  await popup.close();

  await page.getByRole('button', { name: 'Gmail Integration' }).click();
  await expect(page.getByText(/Gmail connection is not configured for this GODFIN build yet/)).toBeVisible();

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
  await expect(page.getByText(/previous six finished calendar months/i)).toBeVisible();
  await expect(page.getByText(/At least 8 full calendar weeks/)).toBeVisible();
  await expect(page.getByText('Not ready yet')).toBeVisible();
});

test('subscriptions hide INR totals when a verified currency rate is unavailable', async ({ page }) => {
  await mockAuthenticatedApp(page);
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Subscriptions', exact: true }).click();

  await expect(page.getByText(/INR totals are hidden instead of estimated/)).toBeVisible();
  await expect(page.getByText('INR conversion unavailable')).toBeVisible();
  await expect(page.getByText('USD service')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh currency rates' }).click();
  await expect(page.getByText(/Could not refresh rates while offline/)).toBeVisible();
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
  await expect(page.getByRole('button', { name: 'Generate & Download AI PDF' })).toBeDisabled();

  await page.getByRole('link', { name: 'Budget', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Add savings' })).toBeVisible();
  await page.getByRole('button', { name: 'Add savings' }).click();
  await expect(page.getByRole('heading', { name: /Update Emergency cushion/ })).toBeVisible();
  await expect(page.getByLabel('Change')).toHaveValue('deposit');
});

test('net worth hides every headline total when one active valuation is unsafe', async ({ page }) => {
  await mockAuthenticatedApp(page, {
    tier: 'max',
    valid: true,
    status: 'active',
    features: ['net_worth'],
    message: 'GODFIN Max is active.',
    topup_credits: 0,
  });
  await page.goto('/pin');
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('link', { name: 'Net Worth', exact: true }).click();

  await expect(page.getByText('Net-worth totals are temporarily hidden')).toBeVisible();
  await expect(page.getByText(/will not relabel an old value or assume currencies are equal/)).toBeVisible();
  await expect(page.getByText('Unavailable')).toHaveCount(4);
  await expect(page.getByText(/Native.*\$100/)).toBeVisible();
  await expect(page.getByText(/No recent verified USD to INR exchange rate/)).toBeVisible();
  await expect(page.getByLabel('Net-worth base currency')).toHaveValue('INR');
});
