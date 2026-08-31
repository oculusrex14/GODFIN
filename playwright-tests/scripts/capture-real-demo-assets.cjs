'use strict';

const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const {
  mkdir,
  readFile,
  writeFile,
} = require('node:fs/promises');
const { chromium } = require('@playwright/test');

// This script intentionally drives the built demo at /demo.  The page is the
// real React application; this small fixture only makes its API boundary
// deterministic if the bundle falls back to network fetches while capturing.
const repositoryRoot = path.resolve(__dirname, '../..');
const baseUrl = (
  process.env.GODFIN_DEMO_BASE_URL
    || process.env.GODFIN_E2E_BASE_URL
    || 'http://127.0.0.1:5300'
).replace(/\/+$/, '');
const outputDirectory = path.resolve(
  process.env.GODFIN_REAL_APP_SCREENSHOT_DIR
    || path.join(repositoryRoot, 'website/public/screenshots/real-app'),
);
const goldenFixturePath = path.join(
  repositoryRoot,
  'backend/tests/fixtures/golden_ledger_v1.json',
);

const FIXED_NOW = Date.parse('2026-07-31T12:00:00+05:30');
const FIXED_NOW_ISO = '2026-07-31T12:00:00+05:30';

const taxonomy = {
  category_names: [
    'FOOD & DINING',
    'HOUSING',
    'TRANSPORTATION',
    'ENTERTAINMENT',
    'UTILITIES & BILLS',
    'FINANCIAL OBLIGATIONS',
    'HEALTH & WELLNESS',
    'EDUCATION',
    'SHOPPING',
    'INCOME',
    'TRANSFERS',
    'MISCELLANEOUS',
  ],
  categories: {
    'FOOD & DINING': { subcategories: ['Groceries', 'Restaurants', 'Coffee/Snacks'] },
    HOUSING: { subcategories: ['Rent', 'Maintenance'] },
    TRANSPORTATION: { subcategories: ['Public Transit', 'Fuel', 'Ride Hailing'] },
    ENTERTAINMENT: { subcategories: ['Subscriptions', 'Movies/Events'] },
    'UTILITIES & BILLS': { subcategories: ['Electricity', 'Internet/Phone'] },
    'FINANCIAL OBLIGATIONS': { subcategories: ['Insurance Premium', 'SIP/Investment'] },
    'HEALTH & WELLNESS': { subcategories: ['Medical/Pharmacy', 'Gym/Fitness'] },
    EDUCATION: { subcategories: ['Courses/Books'] },
    SHOPPING: { subcategories: ['General', 'Clothing'] },
    INCOME: { subcategories: ['Salary', 'Freelance', 'Interest', 'Other Income'] },
    TRANSFERS: { subcategories: ['Own Account Transfer', 'Credit Card Payment'] },
    MISCELLANEOUS: { subcategories: ['Other'] },
  },
};

const transactions = [
  ['salary-2026-07', '2026-07-31', 'SYNTHETIC SALARY', 34000, 'credit', 'INCOME', 'Salary', 'rule'],
  ['freelance-2026-07', '2026-07-15', 'SYNTHETIC FREELANCE', 10000, 'credit', 'INCOME', 'Freelance', 'confirmed_pattern'],
  ['generic-credit-2026-07', '2026-07-14', 'SYNTHETIC GENERIC CREDIT', 7000, 'credit', 'MISCELLANEOUS', 'Other', 'user_confirmed'],
  ['refund-2026-07', '2026-07-13', 'SYNTHETIC REFUND', 1200, 'credit', 'INCOME', 'Refund', 'rule'],
  ['cashback-2026-07', '2026-07-12', 'SYNTHETIC CASHBACK', 100, 'credit', 'INCOME', 'Cashback', 'rule'],
  ['reimbursement-2026-07', '2026-07-11', 'SYNTHETIC REIMBURSEMENT', 300, 'credit', 'MISCELLANEOUS', 'Other', 'user_confirmed'],
  ['reversal-2026-07', '2026-07-10', 'SYNTHETIC REVERSAL', 500, 'credit', 'MISCELLANEOUS', 'Other', 'rule'],
  ['groceries-2026-07', '2026-07-09', 'SYNTHETIC GROCERIES', 8000, 'debit', 'FOOD & DINING', 'Groceries', 'merchant_memory'],
  ['dining-2026-07', '2026-07-08', 'SYNTHETIC DINING', 2000, 'debit', 'FOOD & DINING', 'Restaurants', 'merchant_memory'],
  ['subscription-ledger-2026-07', '2026-07-07', 'SYNTHETIC STREAM', 1000, 'debit', 'ENTERTAINMENT', 'Subscriptions', 'confirmed_pattern'],
  ['transfer-out-2026-07', '2026-07-06', 'SYNTHETIC OWN TRANSFER', 5000, 'debit', 'TRANSFERS', 'Own Account Transfer', 'rule'],
  ['transfer-in-2026-07', '2026-07-06', 'SYNTHETIC OWN TRANSFER', 5000, 'credit', 'TRANSFERS', 'Own Account Transfer', 'rule'],
  ['card-payment-2026-07', '2026-07-05', 'SYNTHETIC CARD PAYMENT', 3000, 'debit', 'TRANSFERS', 'Credit Card Payment', 'rule'],
].map(([id, date, merchant, amount, type, category, subcategory, source]) => ({
  id,
  date,
  merchant_raw: merchant,
  merchant_normalized: merchant,
  raw_text: `Synthetic acceptance ledger: ${merchant}`,
  amount,
  type,
  instrument: 'statement',
  account_id: type === 'credit' && id === 'transfer-in-2026-07'
    ? 'example-card'
    : 'example-savings',
  category,
  subcategory,
  confidence: 1,
  classification_source: source,
  is_locked: false,
  is_transfer: category === 'TRANSFERS',
  is_recurring: id === 'subscription-ledger-2026-07',
  review_required: false,
  status: id === 'reversal-2026-07' ? 'reversal' : 'settled',
}));

const reviewItems = [
  {
    ...transactions[2],
    category: null,
    subcategory: null,
    review_required: true,
    confidence: 0.42,
    classification_reason: 'A generic credit is kept for your review instead of being assumed to be income.',
  },
  {
    id: 'review-small-shop',
    date: '2026-07-04',
    merchant_raw: 'SYNTHETIC LOCAL SHOP',
    merchant_normalized: 'SYNTHETIC LOCAL SHOP',
    amount: 650,
    type: 'debit',
    instrument: 'statement',
    category: null,
    subcategory: null,
    confidence: 0.42,
    review_required: true,
    classification_reason: 'This made-up merchant has not been confirmed in the sample history.',
  },
];

const incomeSources = [
  {
    id: 'income-salary',
    source_name: 'Synthetic salary',
    expected_amount: 40000,
    frequency: 'monthly',
    effective_from: '2026-08-01',
    last_detected_amount: 34000,
    last_detected_date: '2026-07-31',
    next_expected_date: '2026-08-31',
    is_active: true,
    account_id: 'example-savings',
  },
  {
    id: 'income-freelance',
    source_name: 'Synthetic freelance work',
    expected_amount: 10000,
    frequency: 'irregular',
    effective_from: '2026-07-01',
    last_detected_amount: 10000,
    last_detected_date: '2026-07-15',
    is_active: true,
    account_id: 'example-savings',
  },
];

const subscriptions = [
  {
    id: 'subscription-inr',
    name: 'Synthetic learning plan',
    amount: 1000,
    currency: 'INR',
    frequency: 'monthly',
    category: 'EDUCATION',
    subcategory: 'Courses/Books',
    next_payment_date: '2026-09-07',
    is_active: true,
  },
  {
    id: 'subscription-usd',
    name: 'Synthetic productivity plan',
    amount: 10,
    currency: 'USD',
    frequency: 'monthly',
    category: 'UTILITIES & BILLS',
    subcategory: 'Subscriptions',
    next_payment_date: '2026-09-12',
    is_active: true,
    fx_rate_to_inr: 83,
  },
];

const goals = [
  {
    id: 'goal-emergency',
    name: 'Synthetic emergency fund',
    target_amount: 50000,
    current_saved: 8000,
    deadline_date: '2027-06-30',
    pressure_level: 'moderate',
    annual_return_rate: 0,
    minimum_flexible_floor: 5000,
    is_active: true,
  },
  {
    id: 'goal-course',
    name: 'Synthetic professional course',
    target_amount: 90000,
    current_saved: 24000,
    deadline_date: '2027-03-31',
    pressure_level: 'minimal',
    annual_return_rate: 0,
    minimum_flexible_floor: 5000,
    is_active: true,
  },
];

const licenseFeatures = [
  'multiple_accounts',
  'advanced_reports',
  'cash_flow_calendar',
  'net_worth',
  'behavior_insights',
  'advisor',
  'ai_advisor',
  'goal_auto_contributions',
  'ca_tax_pack',
];

const license = {
  tier: 'max',
  licensed_tier: 'max',
  status: 'active',
  valid: true,
  features: licenseFeatures,
  verified_at: '2026-07-31T00:00:00Z',
  offline_grace_until: '2026-08-07T00:00:00Z',
  entitlement_integrity: 'verified',
  monthly_credits: 0,
  hosted_credits_included: 0,
  topup_credits: 0,
  masked_key: 'GODFIN-MAX-••••-DEMO',
  message: 'Synthetic GODFIN Max demo access.',
  website_url: 'https://godfin.dev',
};

const profile = {
  data_status: 'available',
  period_start: '2026-07-01',
  period_end: '2026-07-31',
  complete_month_count: 7,
  verified_income_count: 8,
  spending_transaction_count: 3,
  savings_rate: 75,
  impulse_index: 6.2,
  fixed_expense_ratio: 18.2,
  recurring_burden: 4.2,
  subscription_dependency: 4.2,
  lifestyle_inflation: 3.8,
  metrics: {},
};

const netWorthItems = [
  {
    id: 'cash-asset',
    name: 'Synthetic cash reserve',
    item_type: 'asset',
    asset_class: 'cash',
    valuation_mode: 'manual',
    symbol: null,
    quantity: 1,
    currency: 'INR',
    manual_value: 100000,
    valuation_source: 'Made-up opening balance',
    valued_at: '2026-07-31',
    expires_on: '2026-08-31',
    value_base: 100000,
    native_value: 100000,
    source: 'Made-up opening balance',
    provenance: 'manual_sourced',
    stale: false,
    available: true,
    unavailable_reason: null,
    quote_history: [],
  },
  {
    id: 'quoted-asset',
    name: 'Synthetic listed holding',
    item_type: 'asset',
    asset_class: 'stock',
    valuation_mode: 'market',
    symbol: 'SYNTH',
    quantity: 1,
    currency: 'USD',
    manual_value: null,
    valuation_source: 'Fixed demo quote',
    valued_at: '2026-07-31',
    expires_on: '2026-08-01',
    value_base: 8300,
    native_value: 100,
    source: 'Fixed synthetic quote',
    provenance: 'market_quote',
    stale: false,
    available: true,
    unavailable_reason: null,
    quote_history: [],
  },
  {
    id: 'debt-liability',
    name: 'Synthetic education loan',
    item_type: 'liability',
    asset_class: 'debt',
    valuation_mode: 'manual',
    symbol: null,
    quantity: 1,
    currency: 'INR',
    manual_value: 20000,
    valuation_source: 'Made-up statement',
    valued_at: '2026-07-31',
    expires_on: '2026-08-31',
    value_base: 20000,
    native_value: 20000,
    source: 'Made-up statement',
    provenance: 'manual_sourced',
    stale: false,
    available: true,
    unavailable_reason: null,
    quote_history: [],
  },
];

const reportSummary = {
  total_spend: 11000,
  total_income: 44000,
  savings_rate: 75,
  transaction_count: 13,
  recurring_total: 1830,
  all_categories: [
    { category: 'FOOD & DINING', amount: 10000 },
    { category: 'ENTERTAINMENT', amount: 1000 },
  ],
  spending_by_elasticity: { fixed: 1000, semi_flexible: 2000, flexible: 8000 },
};

const detailedReport = {
  income_breakdown: [
    { source: 'SYNTHETIC SALARY', amount: 34000, percentage: 77.3 },
    { source: 'SYNTHETIC FREELANCE', amount: 10000, percentage: 22.7 },
  ],
  recurring_list: subscriptions.map((item) => ({
    merchant: item.name,
    amount: item.currency === 'USD' ? 830 : item.amount,
    frequency: item.frequency,
    category: item.category,
  })),
  top_merchants: [
    { merchant: 'SYNTHETIC GROCERIES', amount: 8000, count: 1 },
    { merchant: 'SYNTHETIC DINING', amount: 2000, count: 1 },
    { merchant: 'SYNTHETIC STREAM', amount: 1000, count: 1 },
  ],
  category_comparison: [
    { category: 'FOOD & DINING', current: 10000, average: 9400 },
    { category: 'ENTERTAINMENT', current: 1000, average: 1000 },
  ],
};

const behaviorInsights = {
  calculation_version: 'behavior-insights-v2.0-demo',
  window_days: 181,
  window_months: 6,
  period: 'January–June 2026',
  coverage: {
    period_start: '2026-01-01',
    period_end: '2026-06-30',
    calendar_months: 6,
    calendar_month_keys: ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06'],
    observed_months: 6,
    observed_month_keys: ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06'],
    income_months: 6,
    spending_months: 6,
    cash_flow_months: 6,
    observed_full_weeks: 24,
    included_transactions: 36,
    current_month_excluded: true,
    note: 'Only the previous six finished calendar months are considered. GODFIN cannot know whether every statement was imported.',
  },
  metrics: [
    {
      key: 'savings_consistency',
      label: 'Months when income covered spending',
      available: true,
      value: 100,
      unit: '%',
      difficulty: 'easy',
      confidence: 'high',
      meaning: 'How often the money recorded as income was enough for the spending recorded that month.',
      formula: 'covered months ÷ complete income months × 100',
      inputs: 'Verified income and non-transfer spending grouped into complete calendar months.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'Missing imports can change this result.',
      hidden: false,
    },
    {
      key: 'budget_adherence',
      label: 'Months you stayed within your chosen limit',
      available: true,
      value: 83.3,
      unit: '%',
      difficulty: 'easy',
      confidence: 'high',
      meaning: 'How often recorded monthly spending stayed at or below the sample limit.',
      formula: 'months within limit ÷ complete spending months × 100',
      inputs: 'Synthetic monthly limit and non-transfer spending totals.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'This is only as complete as the spending imported for each month.',
      hidden: false,
    },
    {
      key: 'subscription_load',
      label: 'Income already set aside for subscriptions',
      available: true,
      value: 4.2,
      unit: '%',
      difficulty: 'intermediate',
      confidence: 'high',
      meaning: 'How much of an average recorded income month would be used by confirmed subscriptions.',
      formula: 'monthly subscription value ÷ average verified income × 100',
      inputs: 'Confirmed subscriptions, billing frequency, and fixed reference rates.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'Unconfirmed suggestions are excluded.',
      hidden: false,
    },
    {
      key: 'discretionary_ratio',
      label: 'Spending where you had more choice',
      available: true,
      value: 72.7,
      unit: '%',
      difficulty: 'intermediate',
      confidence: 'high',
      meaning: 'The share of recorded spending in flexible areas such as dining and entertainment.',
      formula: 'flexible-category spending ÷ all non-transfer spending × 100',
      inputs: 'Confirmed transaction categories and spending amounts.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'Category choices decide which purchases count as flexible.',
      hidden: false,
    },
    {
      key: 'buffer_coverage',
      label: 'How many months ready-to-use savings may cover',
      available: true,
      value: 9.8,
      unit: 'months',
      difficulty: 'deeper',
      confidence: 'medium',
      meaning: 'A rough comparison between saved cash and average recorded monthly spending.',
      formula: 'active liquid assets ÷ average spending across complete months',
      inputs: 'Synthetic Net Worth cash and non-transfer spending.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'This is not emergency-fund advice.',
      hidden: false,
    },
    {
      key: 'routine_stability',
      label: 'How similar your active money days are each week',
      available: true,
      value: 87.5,
      unit: 'score',
      difficulty: 'deeper',
      confidence: 'medium',
      meaning: 'Whether transactions happen on a similar number of days from week to week.',
      formula: '100 − capped variation in active-day counts',
      inputs: 'Synthetic transaction dates only; amounts and merchants are not used.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'A steady routine is not automatically good or bad.',
      hidden: false,
    },
    {
      key: 'cash_flow_volatility',
      label: 'How much the amount left over changes',
      available: true,
      value: 8.4,
      unit: '%',
      difficulty: 'deeper',
      confidence: 'high',
      meaning: 'Whether the money left after spending is fairly similar each month.',
      formula: 'standard deviation of monthly money left ÷ average absolute money left × 100',
      inputs: 'Complete months containing synthetic verified income and non-transfer spending.',
      period: 'January–June 2026',
      provenance: 'Synthetic demo values calculated locally.',
      caveat: 'A higher number is not a danger score or diagnosis.',
      hidden: false,
    },
  ],
  reflections: [
    {
      key: 'small_purchases',
      title: 'Are small purchases quietly adding up?',
      observation: 'Six flexible purchases of ₹500 or less added up to ₹1,860, or 6.2% of included spending.',
      question: 'Do these purchases still feel worth it when you see their combined total?',
      action: 'Pick one week to notice these purchases without trying to ban them.',
      evidence: 'Six included purchases in January–June 2026.',
      available: true,
      confidence: 'high',
    },
    {
      key: 'weekend_shift',
      title: 'Does your spending change on weekends?',
      observation: 'Average recorded spending per weekend day was ₹780, compared with ₹620 on weekdays.',
      question: 'Is that difference intentional, or does free time make spending easier to overlook?',
      action: 'Before the next weekend, choose one thing you are happy to spend on.',
      evidence: '52 weekend days and 129 weekdays in January–June 2026.',
      available: true,
      confidence: 'high',
    },
    {
      key: 'late_month_spending',
      title: 'What happens near the end of the month?',
      observation: '₹3,420, or 11.4% of included spending, happened on or after the 21st.',
      question: 'Do later-month purchases feel planned, necessary, or like a response to earlier restraint?',
      action: 'Compare this with pay dates and bill dates before drawing a conclusion.',
      evidence: 'Included spending dates in January–June 2026.',
      available: true,
      confidence: 'high',
    },
    {
      key: 'repeat_merchant',
      title: 'Which place appears most often?',
      observation: 'SYNTHETIC GROCERIES appeared 8 times, totalling ₹8,000.',
      question: 'Does this repeat spending support something you value, or is it happening mostly from habit?',
      action: 'Look at the individual purchases before deciding whether anything should change.',
      evidence: '36 included spending transactions in January–June 2026.',
      available: true,
      confidence: 'high',
    },
  ],
  monthly_budget: 12000,
  policy: 'These local, descriptive insights are never used for advertising, pricing, licensing, lending, insurance, or other consequential decisions.',
};

function cashFlowDays() {
  return Array.from({ length: 31 }, (_, index) => {
    const date = `2026-07-${String(index + 1).padStart(2, '0')}`;
    const dayTransactions = transactions.filter((item) => item.date === date && !item.is_transfer);
    const income = dayTransactions
      .filter((item) => item.type === 'credit' && item.category === 'INCOME')
      .reduce((sum, item) => sum + item.amount, 0);
    const spend = dayTransactions
      .filter((item) => item.type === 'debit')
      .reduce((sum, item) => sum + item.amount, 0);
    return {
      date,
      income,
      spend,
      net: income - spend,
      transaction_count: dayTransactions.length,
    };
  });
}

const syntheticResponses = {
  '/health': { status: 'alive', liveness: true, database: 'available', version: '0.1.0-demo' },
  '/auth/status': { is_first_run: false, pin_length: 4 },
  '/auth/verify-pin': { authenticated: true, token: 'godfin-synthetic-demo-session', pin_length: 4 },
  '/onboarding': { completed: true, deferred: false, current_step: 10, tutorial_version: 1 },
  '/license': license,
  '/license/navigation': { tier: 'max', features: licenseFeatures, routes: {} },
  '/taxonomy': taxonomy,
  '/dashboard/months': { months: ['2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02', '2026-01'] },
  '/dashboard/stats': {
    month_spend: 11000,
    month_income: 44000,
    savings_rate: 75,
    review_queue_count: 2,
    account_balance: 147100,
    account_balance_status: 'verified',
    account_balance_as_of: '2026-07-31',
  },
  '/dashboard/category-breakdown': reportSummary.all_categories,
  '/dashboard/spending-trend': [
    { label: 'Feb', spend: 13200, income: 34000 },
    { label: 'Mar', spend: 12400, income: 34000 },
    { label: 'Apr', spend: 11800, income: 34000 },
    { label: 'May', spend: 12900, income: 34000 },
    { label: 'Jun', spend: 12100, income: 34000 },
    { label: 'Jul', spend: 11000, income: 44000 },
  ],
  '/transactions': { items: transactions, total: transactions.length, page: 1, page_size: 50 },
  '/review/stats': { queue_size: 2, auto_accepted: 10, soft_flagged: 2 },
  '/review': { items: reviewItems, total: reviewItems.length, page: 1, page_size: 50 },
  '/accounts': [
    { id: 'example-savings', bank: 'HDFC', account_type: 'savings', last_4_digits: '0000', nickname: 'Example HDFC Savings', is_active: true },
    { id: 'example-card', bank: 'HDFC', account_type: 'credit_card', last_4_digits: '0001', nickname: 'Example HDFC Credit Card', is_active: true },
  ],
  '/accounts/parser-profiles': { profiles: ['hdfc_savings', 'hdfc_credit', 'sbi_savings', 'kotak_savings'] },
  '/accounts/sender-mappings': [],
  '/goals': goals,
  '/goals/goal-emergency/contributions': [
    { id: 'goal-entry-1', goal_id: 'goal-emergency', amount: 10000, contribution_date: '2026-07-01', entry_type: 'deposit', source_type: 'manual', note: 'Synthetic opening contribution', is_voided: false },
    { id: 'goal-entry-2', goal_id: 'goal-emergency', amount: -2000, contribution_date: '2026-07-20', entry_type: 'withdrawal', source_type: 'manual', note: 'Synthetic planned expense', is_voided: false },
  ],
  '/goal-contribution-suggestions': { enabled: true, items: [] },
  '/profile': profile,
  '/recurring': [
    { id: 'recurring-stream', merchant_normalized: 'SYNTHETIC STREAM', avg_amount: 1000, amount_stddev: 0, frequency: 'monthly', avg_interval_days: 30, last_occurrence: '2026-07-07', next_expected: '2026-08-07', times_detected: 3, category: 'ENTERTAINMENT', confidence: 0.98, evidence_count: 3, detection_status: 'active', is_active: true },
    { id: 'recurring-electricity', merchant_normalized: 'SYNTHETIC ELECTRICITY', avg_amount: 1850, amount_stddev: 110, frequency: 'monthly', avg_interval_days: 30, last_occurrence: '2026-07-18', next_expected: '2026-08-18', times_detected: 4, category: 'UTILITIES & BILLS', confidence: 0.86, evidence_count: 4, detection_status: 'active', is_active: true },
  ],
  '/subscriptions': subscriptions,
  '/subscriptions/stats': { total_monthly_cost: 1830, total_annual_projection: 21960, active_count: 2, inactive_count: 0 },
  '/subscriptions/exchange-rates': { base_currency: 'INR', rates: { INR: 1, USD: 83, EUR: 90, GBP: 106 }, fx: { status: 'available', stale: false, as_of: '2026-07-31', provider: 'Fixed synthetic reference' } },
  '/subscriptions/suggestions': [],
  '/subscriptions/suggestions/candidates': [],
  '/subscriptions/reminders': { reminders: subscriptions.map((item) => ({ ...item, days_until: 7 })) },
  '/income': { items: incomeSources, total: incomeSources.length },
  '/income/stats': { total_expected_monthly: 50000, total_detected_this_month: 44000, sources_count: 2, active_sources_count: 2 },
  '/income/coverage': { months: 7, period_start: '2026-01-01', period_end: '2026-07-31', status: 'available' },
  '/reports/summary': reportSummary,
  '/reports/detailed': detailedReport,
  '/reports/ai/insights': {
    month: '2026-07',
    insights: {
      available: true,
      source: 'synthetic_demo',
      executive_summary: 'Verified income covered the included spending in this made-up July, with ₹33,000 left before later decisions.',
      highlights: [
        { label: 'Savings rate', value: '75.0%', tone: 'positive' },
        { label: 'Largest category', value: 'Food & Dining', tone: 'neutral' },
        { label: 'Needs review', value: '2 rows', tone: 'warning' },
      ],
      sections: [
        { title: 'What stood out', tone: 'positive', icon: 'trend', content: 'Included spending was lower than each of the previous five synthetic months.' },
        { title: 'What to review', tone: 'warning', icon: 'review', content: 'Confirm what the generic credit and local-shop purchase represent before finalizing.' },
      ],
      recommendations: ['Review the two uncertain rows.', 'Check whether both recurring plans are still useful.', 'Keep the emergency-fund contribution history up to date.'],
    },
    llm: { provider: 'demo', model: 'synthetic-explanation' },
    consent: { provided: false, version: 'demo-only' },
    generated_at: '2026-07-31T00:00:00Z',
  },
  '/llm/config': [],
  '/llm/providers': [],
  '/cash-flow/calendar': { month: '2026-07', days: cashFlowDays(), total_income: 44000, total_spend: 11000, net: 33000, max_daily_flow: 34000 },
  '/net-worth': { items: netWorthItems, total_assets: 108300, total_liabilities: 20000, net_worth: 88300, base_currency: 'INR', valuation_status: 'complete', stale_count: 0, unavailable_item_count: 0, valued_item_count: 3, item_count: 3, calculation_version: '1.0', provenance: 'Synthetic demo values' },
  '/net-worth/market-data/config/status': { configured: false, provider: 'Twelve Data', base_currency: 'INR', supported_base_currencies: ['INR', 'USD', 'EUR', 'GBP'], key_storage: 'Encrypted locally', privacy: 'No demo key is stored.' },
  '/behavior-insights': behaviorInsights,
  '/behavior-insights/sponsor/card': null,
  '/auth/gmail/status': { connected: false, status: 'not_configured', retryable: false, message: 'Not connected in the synthetic demo.' },
  '/ingest/status': { last_run: '2026-07-31T09:00:00Z', status: 'idle' },
  '/ingest/gmail/sync-status': { status: 'idle', percent: 0, processed: 0, total: 0 },
  '/ingest/scheduler/status': { enabled: false, status: 'disabled' },
  '/system/status': { backend: 'online', database: 'healthy', network_access: false, version: '0.1.0-demo' },
  '/system/embeddings/status': { enabled: false, status: 'disabled', model_installed: false, download_in_progress: false },
  '/system/feature-flags': { local_ai: true, profiles: true, reward_pilot: false, sponsor_card: false, ppp_checkout: false, net_worth: true },
  '/audit/sessions': [],
};

function responseForApiPath(pathname, method = 'GET') {
  if (syntheticResponses[pathname] !== undefined) return syntheticResponses[pathname];
  if (/^\/transactions\//.test(pathname)) return transactions[0];
  if (/^\/review\//.test(pathname)) return { resolved: true };
  if (/^\/goals\/[^/]+\/contributions$/.test(pathname)) return [];
  if (/^\/goals\/[^/]+\/simulate$/.test(pathname)) {
    return {
      required_monthly_saving: 3818.18,
      current_flexible_spend: 8000,
      max_saveable: 33000,
      months_remaining: 11,
      feasibility: 'feasible',
      pressure_levels: { minimal: 3818.18, moderate: 4200, aggressive: 4800 },
      calculation_version: '2.0',
    };
  }
  if (/^\/reports\//.test(pathname)) return syntheticResponses['/reports/summary'];
  if (method !== 'GET') return { ok: true, status: 'saved_in_demo_memory_only' };
  return {};
}

const DETERMINISTIC_STYLE = `
  *, *::before, *::after {
    animation-delay: 0s !important;
    animation-duration: 0s !important;
    animation-iteration-count: 1 !important;
    transition-delay: 0s !important;
    transition-duration: 0s !important;
    scroll-behavior: auto !important;
    caret-color: transparent !important;
  }
`;

async function configureContext(context) {
  // Freeze dates before the React bundle evaluates so dashboard, reports, and
  // the cash-flow calendar all select the same finished synthetic month.
  await context.addInitScript(({ fixedNow, responses }) => {
    const NativeDate = Date;
    class FrozenDate extends NativeDate {
      constructor(...args) {
        if (args.length === 0) {
          super(fixedNow);
        } else {
          super(...args);
        }
      }

      static now() {
        return fixedNow;
      }
    }
    Object.setPrototypeOf(FrozenDate, NativeDate);
    FrozenDate.parse = NativeDate.parse;
    FrozenDate.UTC = NativeDate.UTC;
    window.Date = FrozenDate;

    // demo-main installs its own fetch shim.  Keep this wrapper as the outer
    // boundary so every API call still receives the deterministic fixture.
    const originalFetch = window.fetch.bind(window);
    let delegatedFetch = originalFetch;
    const captureFetch = function captureFetch(input, init = {}) {
      const request = typeof Request !== 'undefined' && input instanceof Request
        ? input
        : null;
      const url = new URL(request?.url || String(input), window.location.origin);
      const marker = '/api/v1';
      const markerIndex = url.pathname.indexOf(marker);
      if (markerIndex < 0) return delegatedFetch.apply(this, arguments);

      const pathname = url.pathname.slice(markerIndex + marker.length) || '/';
      const method = String(init.method || request?.method || 'GET').toUpperCase();
      const payload = responses[pathname] !== undefined
        ? responses[pathname]
        : method === 'GET'
          ? {}
          : { ok: true, status: 'saved_in_demo_memory_only' };
      const isDownload = (
        (pathname.startsWith('/reports/') && /csv|json|pdf|fy\/pack/.test(pathname))
        || pathname === '/behavior-insights/export'
      );
      if (isDownload) {
        return Promise.resolve(new Response('Synthetic GODFIN demo export. No personal data.', {
          status: 200,
          headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        }));
      }
      return Promise.resolve(new Response(JSON.stringify(payload), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-store',
          'X-GODFIN-Demo': 'synthetic',
        },
      }));
    };
    Object.defineProperty(window, 'fetch', {
      configurable: true,
      get() {
        return captureFetch;
      },
      set(nextFetch) {
        delegatedFetch = typeof nextFetch === 'function' ? nextFetch : originalFetch;
      },
    });
  }, { fixedNow: FIXED_NOW, responses: syntheticResponses });

}

async function stabilizePage(page) {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addStyleTag({ content: DETERMINISTIC_STYLE });
  // The badge is the sole disclosure overlay; pure product screenshots omit
  // only this class while leaving all application UI intact.
  await page.addStyleTag({ content: '.godfin-demo-badge { display: none !important; }' });
  await page.evaluate(() => document.activeElement?.blur());
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
  });
  // Recharts uses JavaScript-driven tweening for several charts, so a short
  // settle window is needed even after reduced motion and CSS animation rules.
  await page.waitForTimeout(1800);
  await page.evaluate(() => document.activeElement?.blur());
}

// Visible-text privacy gate.  These patterns are deliberately conservative:
// ordinary dates and INR amounts are allowed, while contact/payment/account
// identifiers fail the capture before a public asset can be written.
const EMAIL_PATTERN = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const PHONE_PATTERN = /(?<!\d)(?:\+?91[\s.-]?)?[6-9]\d{9}(?!\d)/g;
const GROUPED_PHONE_PATTERN = /(?<!\d)\+?\d{1,3}[\s.-]\d{3}[\s.-]\d{3}[\s.-]\d{4}(?!\d)/g;
const UPI_PATTERN = /\b[A-Z0-9][A-Z0-9._-]{1,}@[A-Z][A-Z0-9._-]{1,}\b/gi;
const IFSC_PATTERN = /\b[A-Z]{4}0[A-Z0-9]{6}\b/gi;
const LICENSE_PATTERN = /\b(?:GODFIN|GF)[-_][A-Z0-9]{4,}(?:[-_][A-Z0-9]{4,})+\b/gi;
const LICENSE_LABEL_PATTERN = /\b(?:license|activation|product)\s+(?:key|code)\b\s*[:#-]?\s*[A-Z0-9][A-Z0-9_-]{11,}/gi;
const LONG_ACCOUNT_PATTERN = /\b\d{10,}\b/g;
const LABELED_ACCOUNT_PATTERN = /\b(?:account|acct|a\/c|iban|card)\b[^\n]{0,32}\b\d{8,}\b/gi;

function uniqueMatches(matches) {
  return [...new Set(matches.filter(Boolean).map((match) => match.trim()))];
}

function findSensitiveVisibleText(text) {
  const findings = [];
  const emails = [...text.matchAll(EMAIL_PATTERN)].map(([match]) => match);
  findings.push(
    ...emails
      .filter((match) => match.toLowerCase() !== 'hello@godfin.dev')
      .map((match) => `email:${match}`),
  );
  findings.push(...uniqueMatches([...text.matchAll(PHONE_PATTERN)].map(([match]) => `phone:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(GROUPED_PHONE_PATTERN)].map(([match]) => `phone:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(UPI_PATTERN)].map(([match]) => `upi:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(IFSC_PATTERN)].map(([match]) => `ifsc:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(LICENSE_PATTERN)].map(([match]) => `license:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(LICENSE_LABEL_PATTERN)].map(([match]) => `license:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(LONG_ACCOUNT_PATTERN)].map(([match]) => `account:${match}`)));
  findings.push(...uniqueMatches([...text.matchAll(LABELED_ACCOUNT_PATTERN)].map(([match]) => `account:${match}`)));
  return uniqueMatches(findings);
}

async function assertPublicSafe(page, routeName) {
  const visibleText = await page.locator('body').innerText();
  const findings = findSensitiveVisibleText(visibleText);
  if (findings.length > 0) {
    throw new Error(
      `Sensitive-looking visible text on ${routeName}: ${findings.join(', ')}`,
    );
  }
}

const routes = [
  { route: '/', nav: 'Dashboard', heading: 'Dashboard', content: 'MONTH SPEND', filename: 'dashboard.png' },
  { route: '/upload', nav: 'Upload', heading: 'Upload Statement', content: 'BANK STATEMENT', filename: 'upload.png' },
  { route: '/transactions', nav: 'Transactions', heading: 'Transactions', content: '13 transactions', filename: 'transactions.png' },
  { route: '/review', nav: 'Review', heading: 'Review Queue', content: 'transactions need categorization', filename: 'review.png' },
  { route: '/budget', nav: 'Budget', heading: 'Budget & Goals', content: 'GOALS (2)', filename: 'budget.png' },
  { route: '/subscriptions', nav: 'Subscriptions', heading: 'Subscriptions', content: 'ACTIVE (2)', filename: 'subscriptions.png' },
  { route: '/reports', nav: 'Reports', heading: 'Reports', content: 'YOUR FINANCIAL REPORT', filename: 'reports.png' },
  { route: '/cash-flow', nav: 'Cash Flow', heading: 'Cash-flow Calendar', content: 'Net cash flow', filename: 'cash-flow.png' },
  { route: '/net-worth', nav: 'Net Worth', heading: 'Net Worth', content: 'NET WORTH', filename: 'net-worth.png' },
  { route: '/behavior-insights', nav: 'Behavior Insights', heading: 'Your Money Habits', content: 'Things worth reflecting on', filename: 'behavior-insights.png' },
];

async function waitForRoute(page, target) {
  await page.getByRole('heading', { name: target.heading, exact: true })
    .waitFor({ state: 'visible' });
  await page.getByText(target.content, { exact: false }).first()
    .waitFor({ state: 'visible' });
  await page.getByRole('main').waitFor({ state: 'visible' });
}

async function navigateTo(page, target) {
  const link = page.getByRole('link', { name: target.nav, exact: true });
  await link.waitFor({ state: 'visible' });
  await link.click();
  await page.waitForFunction((expectedRoute) => {
    const pathname = window.location.pathname;
    if (expectedRoute === '/') {
      return /\/demo-app(?:\/index\.html)?\/?$/.test(pathname);
    }
    return pathname.endsWith(`/demo-app${expectedRoute}`);
  }, target.route);
  await waitForRoute(page, target);
}

async function assertPngDimensions(filePath, expected) {
  const png = await readFile(filePath);
  const isPng = png.length >= 24
    && png.readUInt32BE(0) === 0x89504e47
    && png.readUInt32BE(4) === 0x0d0a1a0a;
  if (!isPng) throw new Error(`Expected a PNG screenshot at ${filePath}`);
  const dimensions = { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
  if (dimensions.width !== expected.width || dimensions.height !== expected.height) {
    throw new Error(
      `Unexpected screenshot dimensions for ${filePath}: `
      + `${dimensions.width}x${dimensions.height}; expected ${expected.width}x${expected.height}`,
    );
  }
}

async function captureScreenshot(page, target, screenshotPath, dimensions) {
  await stabilizePage(page);
  await assertPublicSafe(page, target.route);
  await page.screenshot({
    path: screenshotPath,
    animations: 'disabled',
    caret: 'hide',
    fullPage: false,
    scale: 'device',
  });
  await assertPngDimensions(screenshotPath, dimensions);
}

function sourceGitSha() {
  return execFileSync(
    'git',
    ['-C', repositoryRoot, 'rev-parse', 'HEAD'],
    { encoding: 'utf8' },
  ).trim();
}

async function main() {
  await mkdir(outputDirectory, { recursive: true });
  const [fixtureBytes, gitSha] = await Promise.all([
    readFile(goldenFixturePath),
    Promise.resolve(sourceGitSha()),
  ]);
  const fixtureSha256 = createHash('sha256').update(fixtureBytes).digest('hex');

  const browser = await chromium.launch({ headless: true });
  const captures = [];
  try {
    const dashboardContext = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
      locale: 'en-IN',
      timezoneId: 'Asia/Kolkata',
      colorScheme: 'dark',
      reducedMotion: 'reduce',
    });
    await configureContext(dashboardContext);
    const dashboardPage = await dashboardContext.newPage();
    await dashboardPage.goto(`${baseUrl}/demo`, { waitUntil: 'domcontentloaded' });
    // The production demo build starts unlocked.  This fallback keeps the
    // script useful against a non-demo development build as well.
    if (await dashboardPage.getByLabel('Enter your PIN').count()) {
      await dashboardPage.getByLabel('Enter your PIN').fill('4826');
      await dashboardPage.getByRole('button', { name: 'Unlock' }).click();
    }
    await waitForRoute(dashboardPage, routes[0]);
    const dashboardPath = path.join(outputDirectory, 'godfin-dashboard-synthetic-2x.png');
    await captureScreenshot(dashboardPage, routes[0], dashboardPath, { width: 2880, height: 1800 });
    captures.push({
      route: routes[0].route,
      heading: routes[0].heading,
      filename: 'godfin-dashboard-synthetic-2x.png',
      viewport: { width: 1440, height: 900, device_scale_factor: 2 },
      dimensions: { width: 2880, height: 1800 },
    });
    await dashboardContext.close();

    const standardContext = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      deviceScaleFactor: 1,
      locale: 'en-IN',
      timezoneId: 'Asia/Kolkata',
      colorScheme: 'dark',
      reducedMotion: 'reduce',
    });
    await configureContext(standardContext);
    const page = await standardContext.newPage();
    await page.goto(`${baseUrl}/demo`, { waitUntil: 'domcontentloaded' });
    if (await page.getByLabel('Enter your PIN').count()) {
      await page.getByLabel('Enter your PIN').fill('4826');
      await page.getByRole('button', { name: 'Unlock' }).click();
    }
    await waitForRoute(page, routes[0]);
    await captureScreenshot(page, routes[0], path.join(outputDirectory, routes[0].filename), { width: 1920, height: 1080 });
    captures.push({
      route: routes[0].route,
      heading: routes[0].heading,
      filename: routes[0].filename,
      viewport: { width: 1920, height: 1080, device_scale_factor: 1 },
      dimensions: { width: 1920, height: 1080 },
    });
    for (const target of routes.slice(1)) {
      await navigateTo(page, target);
      const screenshotPath = path.join(outputDirectory, target.filename);
      await captureScreenshot(page, target, screenshotPath, { width: 1920, height: 1080 });
      captures.push({
        route: target.route,
        heading: target.heading,
        filename: target.filename,
        viewport: { width: 1920, height: 1080, device_scale_factor: 1 },
        dimensions: { width: 1920, height: 1080 },
      });
    }
    await standardContext.close();

    const provenance = {
      schema_version: 1,
      kind: 'godfin-real-app-demo-capture',
      source_repo_sha: gitSha,
      source_git_sha: gitSha,
      canonical_golden_fixture: 'backend/tests/fixtures/golden_ledger_v1.json',
      canonical_golden_fixture_sha256: fixtureSha256,
      entrypoint: `${baseUrl}/demo`,
      served_demo_route: '/demo-app/index.html',
      deterministic_clock: FIXED_NOW_ISO,
      external_network_required_at_render: false,
      synthetic_data: true,
      privacy_statement: 'Every captured value is synthetic in-memory demo data. No bank, Gmail, payment, account, contact, or personal financial record is used or exported.',
      pure_screenshot_overlay_hidden: '.godfin-demo-badge',
      animation_policy: 'Reduced motion plus zero-duration CSS transitions/animations and Playwright animations disabled.',
      privacy_scan: {
        source: 'visible document.body.innerText after the demo disclosure badge is hidden',
        allowed_email: 'hello@godfin.dev',
        patterns: ['email', 'phone', 'UPI', 'IFSC', 'license key', 'long unmasked account number'],
        result: 'passed',
      },
      screenshots: captures,
    };
    await writeFile(
      path.join(outputDirectory, 'provenance.json'),
      `${JSON.stringify(provenance, null, 2)}\n`,
      'utf8',
    );
    console.log(`Captured ${captures.length} screenshot records in ${outputDirectory}`);
    console.log(`Source ${gitSha}; golden fixture ${fixtureSha256}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
