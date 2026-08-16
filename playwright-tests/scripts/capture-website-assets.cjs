const path = require('node:path');
const { mkdir } = require('node:fs/promises');
const { chromium } = require('@playwright/test');

const baseUrl = process.env.GODFIN_E2E_BASE_URL || 'http://127.0.0.1:5201';
const outputDirectory = path.resolve(
  __dirname,
  '../../website/public/screenshots',
);

const taxonomy = {
  category_names: [
    'Food & Dining',
    'Housing',
    'Transport',
    'Shopping',
    'Income',
  ],
  categories: {
    'Food & Dining': { subcategories: ['Groceries', 'Restaurants'] },
    Housing: { subcategories: ['Rent', 'Utilities'] },
    Transport: { subcategories: ['Fuel', 'Public Transport'] },
    Shopping: { subcategories: ['Household', 'Clothing'] },
    Income: { subcategories: ['Salary', 'Interest'] },
  },
};

const transactions = [
  {
    id: 'txn-1',
    date: '2026-07-26',
    merchant_raw: 'GREEN BASKET',
    merchant_normalized: 'GREEN BASKET',
    amount: 1840,
    type: 'debit',
    category: 'Food & Dining',
    subcategory: 'Groceries',
    classification_source: 'merchant_memory',
    is_locked: false,
  },
  {
    id: 'txn-2',
    date: '2026-07-23',
    merchant_raw: 'METRO TRANSIT',
    merchant_normalized: 'METRO TRANSIT',
    amount: 520,
    type: 'debit',
    category: 'Transport',
    subcategory: 'Public Transport',
    classification_source: 'confirmed_pattern',
    is_locked: false,
  },
  {
    id: 'txn-3',
    date: '2026-07-20',
    merchant_raw: 'SYNTHETIC SALARY',
    merchant_normalized: 'SYNTHETIC SALARY',
    amount: 85000,
    type: 'credit',
    category: 'Income',
    subcategory: 'Salary',
    classification_source: 'rule',
    is_locked: false,
  },
  {
    id: 'txn-4',
    date: '2026-07-18',
    merchant_raw: 'HOME RENT',
    merchant_normalized: 'HOME RENT',
    amount: 24000,
    type: 'debit',
    category: 'Housing',
    subcategory: 'Rent',
    classification_source: 'merchant_memory',
    is_locked: false,
  },
];

const profile = {
  savings_rate: 31.4,
  impulse_index: 8.3,
  fixed_expense_ratio: 36.2,
  recurring_burden: 7.8,
  subscription_dependency: 2.1,
  lifestyle_inflation: 1.5,
};

const goals = [
  {
    id: 'goal-home-buffer',
    name: 'Six-month emergency fund',
    target_amount: 360000,
    current_saved: 145000,
    deadline_date: '2027-06-30',
    annual_return_rate: 0,
  },
  {
    id: 'goal-trip',
    name: 'Family trip',
    target_amount: 120000,
    current_saved: 48000,
    deadline_date: '2027-01-31',
    annual_return_rate: 0.06,
  },
];

const subscriptions = [
  {
    id: 'sub-1',
    name: 'Learning Library',
    amount: 499,
    currency: 'INR',
    frequency: 'monthly',
    category: 'Education',
    next_payment_date: '2026-08-02',
    is_active: true,
  },
  {
    id: 'sub-2',
    name: 'Music Plan',
    amount: 119,
    currency: 'INR',
    frequency: 'monthly',
    category: 'Entertainment',
    next_payment_date: '2026-08-05',
    is_active: true,
  },
];

const baseResponses = {
  '/health': { status: 'alive', liveness: true, database: 'not_checked', version: '0.1.0' },
  '/auth/status': { is_first_run: false, pin_length: 4 },
  '/auth/verify-pin': { authenticated: true, token: 'synthetic-capture-token' },
  '/onboarding': { completed: true, deferred: false, current_step: 10 },
  '/audit/sessions': [],
  '/review/stats': { queue_size: 2 },
  '/ingest/gmail/sync-status': { status: 'idle', percent: 0 },
  '/taxonomy': taxonomy,
  '/transactions': {
    items: transactions,
    total: transactions.length,
    page: 1,
    page_size: 50,
  },
  '/goals': goals,
  '/goal-contribution-suggestions': {
    enabled: true,
    items: [
      {
        id: 'suggestion-1',
        goal_id: 'goal-home-buffer',
        amount: 10000,
      },
    ],
  },
  '/profile': profile,
  '/recurring': [],
  '/subscriptions': subscriptions,
  '/subscriptions/stats': {
    total_monthly_cost: 618,
    total_annual_projection: 7416,
    active_count: 2,
    inactive_count: 0,
    exchange_rates: {},
  },
  '/subscriptions/suggestions': [
    {
      id: 'subscription-suggestion-1',
      merchant: 'SYNTHETIC VIDEO SERVICE',
      avg_amount: 299,
      frequency: 'monthly',
      next_expected: '2026-08-12',
    },
  ],
  '/subscriptions/reminders': {
    reminders: [
      {
        id: 'sub-1',
        name: 'Learning Library',
        amount: 499,
        currency: 'INR',
        days_until: 3,
      },
    ],
  },
  '/license': {
    tier: 'max',
    valid: true,
    status: 'active',
    features: ['advanced_reports'],
    message: 'GODFIN Max is active.',
    topup_credits: 0,
  },
  '/reports/summary': {
    total_spend: 58320,
    total_income: 85000,
    savings_rate: 31.4,
    transaction_count: 42,
    all_categories: [
      { category: 'Housing', amount: 24000 },
      { category: 'Food & Dining', amount: 14250 },
      { category: 'Transport', amount: 8900 },
      { category: 'Shopping', amount: 6370 },
      { category: 'Utilities', amount: 4800 },
    ],
    spending_by_elasticity: {
      fixed: 28800,
      semi_flexible: 14250,
      flexible: 15270,
    },
  },
  '/reports/detailed': {
    category_comparison: [
      { category: 'Housing', current: 24000, average: 24000 },
      { category: 'Food', current: 14250, average: 15100 },
      { category: 'Transport', current: 8900, average: 9400 },
      { category: 'Shopping', current: 6370, average: 7100 },
    ],
  },
  '/reports/ai/insights': {
    month: '2026-07',
    insights: {
      available: true,
      source: 'llm',
      executive_summary:
        'Verified income covered included spending, with ₹26,680 left in this review window.',
      highlights: [
        { label: 'Savings rate', value: '31.4%', tone: 'positive' },
        { label: 'Largest category', value: 'Housing', tone: 'neutral' },
        { label: 'Needs review', value: '2 rows', tone: 'warning' },
      ],
      sections: [],
      recommendations: [
        'Review the two unclassified transactions before finalizing July.',
      ],
    },
    llm: { provider: 'ollama_local', model: 'qwen-test' },
    consent: { provided: true, version: '2026-08-02' },
    generated_at: '2026-08-02T00:00:00Z',
  },
};

function responseFor(pathname) {
  if (baseResponses[pathname] !== undefined) return baseResponses[pathname];
  if (pathname.startsWith('/transactions')) return baseResponses['/transactions'];
  if (pathname.startsWith('/audit/sessions')) return [];
  if (pathname.startsWith('/review')) {
    return { items: [], total: 0, page: 1, page_size: 50 };
  }
  if (pathname.startsWith('/subscriptions/suggestions')) {
    return baseResponses['/subscriptions/suggestions'];
  }
  if (pathname.startsWith('/subscriptions/reminders')) {
    return baseResponses['/subscriptions/reminders'];
  }
  if (pathname.startsWith('/reports/summary')) {
    return baseResponses['/reports/summary'];
  }
  if (pathname.startsWith('/reports/detailed')) {
    return baseResponses['/reports/detailed'];
  }
  if (pathname.startsWith('/reports/ai/insights')) {
    return baseResponses['/reports/ai/insights'];
  }
  return {};
}

async function capture(page, navigationLabel, heading, fileName) {
  await page
    .getByRole('link', { name: navigationLabel, exact: true })
    .click();
  await page.getByRole('heading', { name: heading, exact: true }).waitFor();
  await page.waitForTimeout(450);
  await page.screenshot({
    path: path.join(outputDirectory, fileName),
    animations: 'disabled',
  });
}

async function main() {
  await mkdir(outputDirectory, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1244, height: 716 },
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname.slice('/api/v1'.length);
    await route.fulfill({ json: responseFor(pathname) });
  });

  await page.goto(`${baseUrl}/pin`);
  await page.getByLabel('Enter your PIN').fill('4826');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await page.getByRole('heading', { name: 'Dashboard' }).waitFor();

  await capture(page, 'Upload', 'Upload Statement', 'import.png');
  await capture(page, 'Transactions', 'Transactions', 'classification.png');
  await capture(page, 'Budget', 'Budget & Goals', 'goals.png');
  await capture(page, 'Subscriptions', 'Subscriptions', 'recurring.png');
  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  await page.getByRole('heading', { name: 'Reports', exact: true }).waitFor();
  await page
    .getByRole('button', { name: 'Download CA Tax Pack' })
    .scrollIntoViewIfNeeded();
  await page.waitForTimeout(450);
  await page.screenshot({
    path: path.join(outputDirectory, 'ca-tax-pack.png'),
    animations: 'disabled',
  });

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
