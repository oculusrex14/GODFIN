const DEMO_ORIGIN = 'https://demo.local';

const taxonomy = {
  category_names: [
    'HOUSING',
    'TRANSPORTATION',
    'FOOD & DINING',
    'UTILITIES & BILLS',
    'FINANCIAL OBLIGATIONS',
    'HEALTH & WELLNESS',
    'SHOPPING',
    'ENTERTAINMENT',
    'EDUCATION',
    'TRANSFERS',
    'INCOME',
    'MISCELLANEOUS',
  ],
  categories: {
    HOUSING: { elasticity: 'fixed', subcategories: ['Rent', 'Maintenance/Society', 'Home Repairs'], confidence_threshold: 0.85 },
    TRANSPORTATION: { elasticity: 'semi_flexible', subcategories: ['Fuel', 'Public Transit', 'Ride Hailing', 'Parking/Tolls'], confidence_threshold: 0.85 },
    'FOOD & DINING': { elasticity: 'flexible', subcategories: ['Groceries', 'Food Delivery', 'Restaurants', 'Coffee/Snacks', 'Canteen'], confidence_threshold: 0.85 },
    'UTILITIES & BILLS': { elasticity: 'semi_flexible', subcategories: ['Electricity', 'Water', 'Internet/Phone', 'Gas', 'Subscriptions'], confidence_threshold: 0.85 },
    'FINANCIAL OBLIGATIONS': { elasticity: 'fixed', subcategories: ['EMI - Loan', 'EMI - Credit Card', 'Insurance Premium', 'SIP/Investment', 'Bank Charges'], confidence_threshold: 0.95 },
    'HEALTH & WELLNESS': { elasticity: 'semi_flexible', subcategories: ['Medical/Pharmacy', 'Gym/Fitness', 'Personal Care', 'Hospital'], confidence_threshold: 0.85 },
    SHOPPING: { elasticity: 'flexible', subcategories: ['Clothing', 'Electronics', 'Home/Kitchen', 'General', 'Online Shopping'], confidence_threshold: 0.85 },
    ENTERTAINMENT: { elasticity: 'flexible', subcategories: ['Subscriptions', 'Movies/Events', 'Gaming', 'Sports'], confidence_threshold: 0.85 },
    EDUCATION: { elasticity: 'semi_flexible', subcategories: ['Courses/Books', 'Software/Tools'], confidence_threshold: 0.85 },
    TRANSFERS: { elasticity: 'none', subcategories: ['Credit Card Payment', 'Own Account Transfer', 'Investment Transfer'], confidence_threshold: 0.95, exclude_from_spend: true },
    INCOME: { elasticity: 'none', subcategories: ['Salary', 'Freelance', 'Refund', 'Cashback', 'Interest', 'Other Income'], confidence_threshold: 0.9, is_income: true },
    MISCELLANEOUS: { elasticity: 'flexible', subcategories: ['Personal', 'Gifts', 'Donations', 'Other'], confidence_threshold: 0.8 },
  },
};

const transactionRows = [
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
  account_id: type === 'credit' && id === 'transfer-in-2026-07' ? 'example-card' : 'example-savings',
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

const incomeSources = [
  { id: 'income-salary', source_name: 'Synthetic salary', expected_amount: 40000, frequency: 'monthly', effective_from: '2026-08-01', last_detected_amount: 34000, last_detected_date: '2026-07-31', next_expected_date: '2026-08-31', is_active: true, account_id: 'example-savings' },
  { id: 'income-freelance', source_name: 'Synthetic freelance work', expected_amount: 10000, frequency: 'irregular', effective_from: '2026-07-01', last_detected_amount: 10000, last_detected_date: '2026-07-15', is_active: true, account_id: 'example-savings' },
];

const subscriptions = [
  { id: 'subscription-inr', name: 'Synthetic learning plan', amount: 1000, currency: 'INR', frequency: 'monthly', category: 'EDUCATION', subcategory: 'Courses/Books', next_payment_date: '2026-09-07', is_active: true },
  { id: 'subscription-usd', name: 'Synthetic productivity plan', amount: 10, amount_inr: 830, currency: 'USD', frequency: 'monthly', category: 'UTILITIES & BILLS', subcategory: 'Subscriptions', next_payment_date: '2026-09-12', is_active: true, fx_rate_to_inr: 83 },
];

const goals = [
  { id: 'goal-emergency', name: 'Synthetic emergency fund', target_amount: 50000, current_saved: 8000, deadline_date: '2027-06-30', pressure_level: 'moderate', annual_return_rate: 0, minimum_flexible_floor: 5000, is_active: true },
  { id: 'goal-course', name: 'Synthetic professional course', target_amount: 90000, current_saved: 24000, deadline_date: '2027-03-31', pressure_level: 'minimal', annual_return_rate: 0, minimum_flexible_floor: 5000, is_active: true },
];

const navFeatures = [
  'multiple_accounts', 'advanced_reports', 'cash_flow_calendar', 'net_worth',
  'behavior_insights', 'advisor', 'ai_advisor', 'goal_auto_contributions', 'ca_tax_pack',
];

const license = {
  tier: 'max', licensed_tier: 'max', status: 'active', valid: true,
  features: navFeatures, verified_at: '2026-07-31T00:00:00Z',
  offline_grace_until: '2026-09-07T00:00:00Z', entitlement_integrity: 'verified',
  monthly_credits: 0, hosted_credits_included: 0, topup_credits: 0,
  masked_key: 'GODFIN-MAX-••••-DEMO', message: 'Synthetic GODFIN Max demo access.',
  website_url: 'https://godfin.dev',
};

const profile = {
  data_status: 'available', period_start: '2026-07-01', period_end: '2026-07-31',
  complete_month_count: 7, verified_income_count: 8, spending_transaction_count: 3,
  savings_rate: 75, impulse_index: 6.2, fixed_expense_ratio: 18.2,
  recurring_burden: 4.2, subscription_dependency: 4.2, lifestyle_inflation: 3.8,
  metrics: {},
};

const netWorthItems = [
  { id: 'cash-asset', name: 'Synthetic cash reserve', item_type: 'asset', asset_class: 'cash', valuation_mode: 'manual', symbol: null, quantity: 1, currency: 'INR', manual_value: 100000, valuation_source: 'Made-up opening balance', valued_at: '2026-07-31', expires_on: '2026-08-31', value_base: 100000, native_value: 100000, source: 'Made-up opening balance', provenance: 'manual_sourced', stale: false, available: true, unavailable_reason: null, quote_history: [] },
  { id: 'quoted-asset', name: 'Synthetic listed holding', item_type: 'asset', asset_class: 'stock', valuation_mode: 'market', symbol: 'SYNTH', quantity: 1, currency: 'USD', manual_value: null, valuation_source: 'Fixed demo quote', valued_at: '2026-07-31', expires_on: '2026-08-01', value_base: 8300, native_value: 100, source: 'Fixed synthetic quote', provenance: 'market_quote', stale: false, available: true, unavailable_reason: null, quote_history: [] },
  { id: 'debt-liability', name: 'Synthetic education loan', item_type: 'liability', asset_class: 'debt', valuation_mode: 'manual', symbol: null, quantity: 1, currency: 'INR', manual_value: 20000, valuation_source: 'Made-up statement', valued_at: '2026-07-31', expires_on: '2026-08-31', value_base: 20000, native_value: 20000, source: 'Made-up statement', provenance: 'manual_sourced', stale: false, available: true, unavailable_reason: null, quote_history: [] },
];

const reportSummary = {
  total_spend: 11000, total_income: 44000, savings_rate: 75, transaction_count: 13,
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
  recurring_list: subscriptions.map((item) => ({ merchant: item.name, amount: item.currency === 'USD' ? 830 : item.amount, frequency: item.frequency })),
  top_merchants: [
    { merchant: 'SYNTHETIC GROCERIES', amount: 8000 },
    { merchant: 'SYNTHETIC DINING', amount: 2000 },
    { merchant: 'SYNTHETIC STREAM', amount: 1000 },
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
      key: 'savings_consistency', label: 'Months when income covered spending', available: true,
      value: 100, unit: '%', difficulty: 'easy', confidence: 'high', hidden: false,
      meaning: 'How often the money recorded as income was enough for the spending recorded that month.',
      formula: 'covered months ÷ complete income months × 100',
      inputs: 'Verified income and non-transfer spending grouped into complete calendar months.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'Missing imports can change this result.',
    },
    {
      key: 'budget_adherence', label: 'Months you stayed within your chosen limit', available: true,
      value: 83.3, unit: '%', difficulty: 'easy', confidence: 'high', hidden: false,
      meaning: 'How often recorded monthly spending stayed at or below the sample limit.',
      formula: 'months within limit ÷ complete spending months × 100',
      inputs: 'Synthetic monthly limit and non-transfer spending totals.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'This is only as complete as the spending imported for each month.',
    },
    {
      key: 'subscription_load', label: 'Income already set aside for subscriptions', available: true,
      value: 4.2, unit: '%', difficulty: 'intermediate', confidence: 'high', hidden: false,
      meaning: 'How much of an average recorded income month would be used by confirmed subscriptions.',
      formula: 'monthly subscription value ÷ average verified income × 100',
      inputs: 'Confirmed subscriptions, billing frequency, and fixed reference rates.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'Unconfirmed suggestions are excluded.',
    },
    {
      key: 'discretionary_ratio', label: 'Spending where you had more choice', available: true,
      value: 72.7, unit: '%', difficulty: 'intermediate', confidence: 'high', hidden: false,
      meaning: 'The share of recorded spending in flexible areas such as dining and entertainment.',
      formula: 'flexible-category spending ÷ all non-transfer spending × 100',
      inputs: 'Confirmed transaction categories and spending amounts.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'Category choices decide which purchases count as flexible.',
    },
    {
      key: 'buffer_coverage', label: 'How many months ready-to-use savings may cover', available: true,
      value: 9.8, unit: 'months', difficulty: 'deeper', confidence: 'medium', hidden: false,
      meaning: 'A rough comparison between saved cash and average recorded monthly spending.',
      formula: 'active liquid assets ÷ average spending across complete months',
      inputs: 'Synthetic Net Worth cash and non-transfer spending.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'This is not emergency-fund advice.',
    },
    {
      key: 'routine_stability', label: 'How similar your active money days are each week', available: true,
      value: 87.5, unit: 'score', difficulty: 'deeper', confidence: 'medium', hidden: false,
      meaning: 'Whether transactions happen on a similar number of days from week to week.',
      formula: '100 − capped variation in active-day counts',
      inputs: 'Synthetic transaction dates only; amounts and merchants are not used.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'A steady routine is not automatically good or bad.',
    },
    {
      key: 'cash_flow_volatility', label: 'How much the amount left over changes', available: true,
      value: 8.4, unit: '%', difficulty: 'deeper', confidence: 'high', hidden: false,
      meaning: 'Whether the money left after spending is fairly similar each month.',
      formula: 'standard deviation of monthly money left ÷ average absolute money left × 100',
      inputs: 'Complete months containing synthetic verified income and non-transfer spending.',
      period: 'January–June 2026', provenance: 'Synthetic demo values calculated locally.',
      caveat: 'A higher number is not a danger score or diagnosis.',
    },
  ],
  reflections: [
    {
      key: 'small_purchases', title: 'Are small purchases quietly adding up?', available: true, confidence: 'high',
      observation: 'Six flexible purchases of ₹500 or less added up to ₹1,860, or 6.2% of included spending.',
      question: 'Do these purchases still feel worth it when you see their combined total?',
      action: 'Pick one week to notice these purchases without trying to ban them.',
      evidence: 'Six included purchases in January–June 2026.',
    },
    {
      key: 'weekend_shift', title: 'Does your spending change on weekends?', available: true, confidence: 'high',
      observation: 'Average recorded spending per weekend day was ₹780, compared with ₹620 on weekdays.',
      question: 'Is that difference intentional, or does free time make spending easier to overlook?',
      action: 'Before the next weekend, choose one thing you are happy to spend on.',
      evidence: '52 weekend days and 129 weekdays in January–June 2026.',
    },
    {
      key: 'late_month_spending', title: 'What happens near the end of the month?', available: true, confidence: 'high',
      observation: '₹3,420, or 11.4% of included spending, happened on or after the 21st.',
      question: 'Do later-month purchases feel planned, necessary, or like a response to earlier restraint?',
      action: 'Compare this with pay dates and bill dates before drawing a conclusion.',
      evidence: 'Included spending dates in January–June 2026.',
    },
    {
      key: 'repeat_merchant', title: 'Which place appears most often?', available: true, confidence: 'high',
      observation: 'SYNTHETIC GROCERIES appeared 8 times, totalling ₹8,000.',
      question: 'Does this repeat spending support something you value, or is it happening mostly from habit?',
      action: 'Look at the individual purchases before deciding whether anything should change.',
      evidence: '36 included spending transactions in January–June 2026.',
    },
  ],
  monthly_budget: 12000,
  policy: 'These local, descriptive insights are never used for advertising, pricing, licensing, lending, insurance, or other consequential decisions.',
};

function daysInMonth(month = '2026-07') {
  const count = new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0).getDate();
  return Array.from({ length: count }, (_, index) => {
    const date = `${month}-${String(index + 1).padStart(2, '0')}`;
    const matches = transactionRows.filter((row) => row.date === date && !row.is_transfer);
    const income = matches.filter((row) => row.type === 'credit' && row.category === 'INCOME').reduce((sum, row) => sum + row.amount, 0);
    const spend = matches.filter((row) => row.type === 'debit').reduce((sum, row) => sum + row.amount, 0);
    return { date, income, spend, net: income - spend, transaction_count: matches.length };
  });
}

function responsePayload(pathname, method) {
  const permittedDemoAction = pathname === '/auth/verify-pin'
    || pathname === '/reports/ai/insights'
    || /^\/goals\/[^/]+\/simulate$/.test(pathname)
    || pathname === '/recurring/detect'
    || pathname === '/transfers/scan';
  if (method !== 'GET' && !permittedDemoAction) {
    return {
      __demo_read_only: true,
      code: 'SYNTHETIC_DEMO_READ_ONLY',
      message: 'This public demo is read-only. Explore every screen without changing the made-up household.',
      hint: 'Install GODFIN to save changes on your own computer.',
      retriable: false,
    };
  }
  if (pathname === '/health') return { status: 'alive', liveness: true, database: 'available', version: '0.1.0-demo' };
  if (pathname === '/auth/status') return { is_first_run: false, pin_length: 4 };
  if (pathname.startsWith('/auth/verify-pin')) return { authenticated: true, token: 'godfin-synthetic-demo-session', pin_length: 4 };
  if (pathname === '/onboarding') return { completed: true, deferred: false, current_step: 10, tutorial_version: 1 };
  if (pathname === '/license') return license;
  if (pathname === '/license/navigation') return { tier: 'max', features: navFeatures, routes: {} };
  if (pathname === '/taxonomy') return taxonomy;
  if (pathname === '/dashboard/months') return { months: ['2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02', '2026-01'] };
  if (pathname === '/dashboard/stats') return { month_spend: 11000, month_income: 44000, savings_rate: 75, review_queue_count: 2, account_balance: 147100, account_balance_status: 'verified', account_balance_as_of: '2026-07-31' };
  if (pathname === '/dashboard/category-breakdown') return reportSummary.all_categories;
  if (pathname === '/dashboard/spending-trend') return [
    { label: 'Feb', spend: 13200, income: 34000 }, { label: 'Mar', spend: 12400, income: 34000 },
    { label: 'Apr', spend: 11800, income: 34000 }, { label: 'May', spend: 12900, income: 34000 },
    { label: 'Jun', spend: 12100, income: 34000 }, { label: 'Jul', spend: 11000, income: 44000 },
  ];
  if (pathname.startsWith('/dashboard/trends/categories')) return [];
  if (pathname.startsWith('/dashboard/trends')) return [];
  if (pathname === '/transactions' || pathname.startsWith('/transactions?')) return { items: transactionRows, total: transactionRows.length, page: 1, page_size: 50 };
  if (/^\/transactions\/[^/]+$/.test(pathname)) return transactionRows.find((row) => pathname.endsWith(row.id)) || transactionRows[0];
  if (pathname === '/review/stats') return { queue_size: 2, auto_accepted: 10, soft_flagged: 2 };
  if (pathname === '/review') return { items: [
    { ...transactionRows[2], category: null, subcategory: null, review_required: true },
    { id: 'review-small-shop', date: '2026-07-04', merchant_raw: 'SYNTHETIC LOCAL SHOP', merchant_normalized: 'SYNTHETIC LOCAL SHOP', amount: 650, type: 'debit', instrument: 'statement', category: null, subcategory: null, confidence: 0.42, review_required: true },
  ], total: 2, page: 1, page_size: 50 };
  if (pathname.startsWith('/review/')) return { resolved: true };
  if (pathname === '/accounts') return [
    { id: 'example-savings', bank: 'HDFC', account_type: 'savings', last_4_digits: '0000', nickname: 'Example HDFC Savings', is_active: true },
    { id: 'example-card', bank: 'HDFC', account_type: 'credit_card', last_4_digits: '0001', nickname: 'Example HDFC Credit Card', is_active: true },
  ];
  if (pathname === '/accounts/parser-profiles') return [
    { profile: 'hdfc_savings', bank: 'HDFC', account_type: 'savings', statement_type: 'hdfc_savings', formats: ['pdf', 'xls', 'xlsx'] },
    { profile: 'hdfc_credit', bank: 'HDFC', account_type: 'credit_card', statement_type: 'hdfc_credit_card', formats: ['pdf'] },
    { profile: 'kotak_savings', bank: 'KOTAK', account_type: 'savings', statement_type: 'kotak_savings', formats: ['pdf'] },
    { profile: 'sbi_savings', bank: 'SBI', account_type: 'savings', statement_type: 'sbi_savings', formats: ['pdf'] },
  ];
  if (pathname === '/accounts/sender-mappings') return [];
  if (pathname === '/goals') return goals;
  if (pathname === '/goals/goal-emergency/contributions') return [
    { id: 'goal-entry-1', goal_id: 'goal-emergency', amount: 10000, contribution_date: '2026-07-01', entry_type: 'deposit', source_type: 'manual', note: 'Synthetic opening contribution', is_voided: false },
    { id: 'goal-entry-2', goal_id: 'goal-emergency', amount: -2000, contribution_date: '2026-07-20', entry_type: 'withdrawal', source_type: 'manual', note: 'Synthetic planned expense', is_voided: false },
  ];
  if (/^\/goals\/[^/]+\/contributions$/.test(pathname)) return [];
  if (/^\/goals\/[^/]+\/simulate$/.test(pathname)) return { required_monthly_saving: 3818.18, current_flexible_spend: 8000, max_saveable: 33000, months_remaining: 11, feasibility: 'feasible', pressure_levels: { minimal: 3818.18, moderate: 4200, aggressive: 4800 }, calculation_version: '2.0', assumptions: ['0% expected return', 'End-of-month contributions'], coverage_months: 6, baseline_surplus: 23000, reducible_spend: 10000 };
  if (pathname === '/goal-contribution-suggestions') return { enabled: true, items: [] };
  if (pathname === '/profile') return profile;
  if (pathname === '/recurring') return [
    { id: 'recurring-stream', merchant_normalized: 'SYNTHETIC STREAM', avg_amount: 1000, amount_stddev: 0, frequency: 'monthly', avg_interval_days: 30, last_occurrence: '2026-07-07', next_expected: '2026-08-07', times_detected: 3, category: 'ENTERTAINMENT', confidence: 0.98, evidence_count: 3, detection_status: 'active', is_active: true },
    { id: 'recurring-electricity', merchant_normalized: 'SYNTHETIC ELECTRICITY', avg_amount: 1850, amount_stddev: 110, frequency: 'monthly', avg_interval_days: 30, last_occurrence: '2026-07-18', next_expected: '2026-08-18', times_detected: 4, category: 'UTILITIES & BILLS', confidence: 0.86, evidence_count: 4, detection_status: 'active', is_active: true },
  ];
  if (pathname === '/recurring/detect') return { created: 0, updated: 2, deactivated: 0, scanned: 7 };
  if (pathname === '/subscriptions') return subscriptions;
  if (pathname === '/subscriptions/stats') return { total_monthly_cost: 1830, total_annual_projection: 21960, active_count: 2, inactive_count: 0 };
  if (pathname === '/subscriptions/exchange-rates') return { base_currency: 'INR', rates: { INR: 1, USD: 83, EUR: 90, GBP: 106 }, fx: { status: 'available', stale: false, as_of: '2026-07-31', provider: 'Fixed synthetic reference' } };
  if (pathname === '/subscriptions/suggestions') return [];
  if (pathname === '/subscriptions/suggestions/candidates') return [];
  if (pathname === '/subscriptions/reminders') return { reminders: subscriptions.map((item) => ({ ...item, days_until: 7 })) };
  if (pathname === '/income') return { items: incomeSources, total: incomeSources.length };
  if (pathname === '/income/stats') return { total_expected_monthly: 50000, total_detected_this_month: 44000, sources_count: 2, active_sources_count: 2 };
  if (pathname === '/income/coverage') return { months: 7, period_start: '2026-01-01', period_end: '2026-07-31', status: 'available' };
  if (pathname === '/reports/summary') return reportSummary;
  if (pathname === '/reports/detailed') return detailedReport;
  if (pathname === '/reports/ai/insights') return { month: '2026-07', insights: { available: true, source: 'synthetic_demo', executive_summary: 'Verified income covered the included spending in this made-up July, with ₹33,000 left before any later decisions.', highlights: [
    { label: 'Savings rate', value: '75.0%', tone: 'positive' }, { label: 'Largest category', value: 'Food & Dining', tone: 'neutral' }, { label: 'Needs review', value: '2 rows', tone: 'warning' },
  ], sections: [
    { title: 'What stood out', tone: 'positive', icon: 'trend', content: 'Included spending was lower than each of the previous five synthetic months.' },
    { title: 'What to review', tone: 'warning', icon: 'review', content: 'Confirm what the generic credit and local-shop purchase represent before finalizing.' },
  ], recommendations: ['Review the two uncertain rows.', 'Check whether both recurring plans are still useful.', 'Keep the emergency-fund contribution history up to date.'] }, llm: { provider: 'demo', model: 'synthetic-explanation' }, consent: { provided: false, version: 'demo-only' }, generated_at: '2026-07-31T00:00:00Z' };
  if (pathname === '/llm/config') return {
    id: 'demo-llm',
    provider: 'ollama_local',
    auth_method: 'none',
    model: 'qwen3:4b',
    base_url: 'http://127.0.0.1:11434',
    is_active: true,
    has_api_key: false,
    is_local: true,
    hosted_data_consent: false,
    consent_version: 'demo-only',
    created_at: '2026-07-01T09:00:00Z',
    updated_at: '2026-07-31T09:00:00Z',
  };
  if (pathname === '/llm/providers') return {
    ollama_local: {
      name: 'Ollama (Local)',
      is_local: true,
      auth_methods: ['none'],
      requires_auth: false,
      models: {
        manual: true,
        suggestions: ['qwen3:1.7b', 'qwen3:4b', 'qwen3:8b', 'qwen3.6:27b', 'qwen3.6:35b-a3b'],
      },
      description: 'Run models locally on your machine',
    },
  };
  if (pathname === '/cash-flow/calendar') { const days = daysInMonth(); return { month: '2026-07', days, total_income: 44000, total_spend: 11000, net: 33000, max_daily_flow: 34000 }; }
  if (pathname === '/transfers') return [{ id: 'transfer-match-1', amount: 5000, confidence: 0.99, date_gap_days: 0, debit: { id: 'transfer-out-2026-07', merchant: 'SYNTHETIC OWN TRANSFER', account: 'Example HDFC Savings · ••••0000', date: '2026-07-06', amount: 5000 }, credit: { id: 'transfer-in-2026-07', merchant: 'SYNTHETIC OWN TRANSFER', account: 'Example HDFC Credit Card · ••••0001', date: '2026-07-06', amount: 5000 } }];
  if (pathname === '/transfers/scan') return { created: 0, updated: 1, deactivated: 0, scanned: 13 };
  if (pathname === '/audit/sessions') return [];
  if (pathname === '/audit/month-status') return { status: 'draft', locked: false };
  if (pathname === '/advisor/digest') return { generated_at: '2026-07-31T00:00:00Z', current_spend: 11000, spending_velocity_percent: -9.1, spending_velocity_message: 'This made-up month is moving more slowly than the previous synthetic baseline.', anomalies: [{ transaction_id: 'review-small-shop', merchant: 'SYNTHETIC LOCAL SHOP', amount: 650 }], budget_breaches: [], upcoming: ['Synthetic productivity plan · ₹830 reference value'], actions: ['Review the two uncertain rows', 'Check the emergency-fund goal'] };
  if (pathname === '/advisor/digest/settings') return { enabled: false, recipient: '', weekday: 1, hour: 9, gmail_connected: false, gmail_send_supported: false };
  if (pathname === '/settings') return { timezone: 'Asia/Kolkata', allow_network_access: false, developer_mode: false, enable_embeddings: false, backup_directory: 'Stored privately on this computer' };
  if (pathname === '/settings/health') return { gmail: { status: 'not_connected', label: 'Not connected' }, llm: { status: 'healthy', label: 'Private local model ready' }, backup: { status: 'healthy', label: 'Demo backup ready' }, database: { status: 'healthy', label: 'Local data available' } };
  if (pathname === '/settings/developer') return { enabled: false, classification_health: { source_counts: { merchant_memory: 2, confirmed_pattern: 2, rule: 7 }, total: 11 }, rules: [] };
  if (pathname === '/settings/backups') return [{ filename: 'godfin-demo-2026-07-31.db', size_bytes: 248832, created_at: '2026-07-31T09:30:00Z' }];
  if (pathname === '/system/status') return { backend: 'online', database: 'healthy', network_access: false, version: '0.1.0-demo' };
  if (pathname === '/system/embeddings/status') return { enabled: false, status: 'disabled', model_installed: false, download_in_progress: false };
  if (pathname === '/system/feature-flags') return { local_ai: true, profiles: true, reward_pilot: false, sponsor_card: false, ppp_checkout: false, net_worth: true };
  if (pathname === '/system/local-ai/profile') return { os: 'macOS', architecture: 'arm64', total_memory_gb: 16, available_memory_gb: 8, free_disk_gb: 120, ollama_installed: true, recommended_model: 'Validated Qwen 4B-class fallback', expected_speed: 'Comfortable for short explanations' };
  if (pathname === '/system/local-ai/download') return { status: 'idle', percent: 0 };
  if (pathname === '/settings/classification-memory') return { items: [], total: 0, personal_model: { eligible: false, confirmed_corrections: 11, required_corrections: 200 } };
  if (pathname === '/auth/gmail/status') return { connected: false, status: 'not_configured', retryable: false, message: 'Not connected in the synthetic demo.' };
  if (pathname === '/ingest/status') return { last_run: '2026-07-31T09:00:00Z', status: 'idle' };
  if (pathname === '/ingest/gmail/sync-status') return { status: 'idle', percent: 0, processed: 0, total: 0 };
  if (pathname === '/ingest/scheduler/status') return { enabled: false, status: 'disabled' };
  if (pathname === '/ingest/gmail/coverage') return { connected: false, covered_from: null, covered_to: null };
  if (pathname === '/net-worth') return { items: netWorthItems, total_assets: 108300, total_liabilities: 20000, net_worth: 88300, base_currency: 'INR', valuation_status: 'complete', stale_count: 0, unavailable_item_count: 0, valued_item_count: 3, item_count: 3, calculation_version: '1.0', provenance: 'Synthetic demo values' };
  if (pathname === '/net-worth/market-data/config/status') return { configured: false, provider: 'Twelve Data', base_currency: 'INR', supported_base_currencies: ['INR', 'USD', 'EUR', 'GBP'], key_storage: 'Encrypted locally', privacy: 'No demo key is stored.' };
  if (pathname === '/behavior-insights') return behaviorInsights;
  if (pathname === '/behavior-insights/sponsor/card') return null;
  if (pathname === '/reward-pilot/status') return { enabled: false, consented: false, status: 'closed' };
  return {};
}

function normalizeApiPath(url) {
  const apiMarker = '/api/v1';
  const index = url.pathname.indexOf(apiMarker);
  return index >= 0 ? url.pathname.slice(index + apiMarker.length) || '/' : null;
}

export function installDemoTransport() {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request?.url || String(input), window.location.origin || DEMO_ORIGIN);
    const pathname = normalizeApiPath(url);
    if (pathname == null) return nativeFetch(input, init);
    const method = String(init.method || request?.method || 'GET').toUpperCase();
    const payload = responsePayload(pathname, method);
    if (payload?.__demo_read_only) {
      const { __demo_read_only: _marker, ...error } = payload;
      return new Response(JSON.stringify(error), {
        status: 409,
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-store',
          'X-GODFIN-Demo': 'synthetic-read-only',
        },
      });
    }
    const download = pathname.startsWith('/reports/') && ['csv', 'json', 'pdf', 'fy/pack'].some((part) => pathname.includes(part));
    if (download) {
      return new Response('Synthetic GODFIN demo export. No personal data.', {
        status: 200,
        headers: { 'Content-Type': 'application/octet-stream' },
      });
    }
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
        'X-GODFIN-Demo': 'synthetic',
      },
    });
  };
}
