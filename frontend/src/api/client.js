const API_BASE = window.location.protocol === 'godfin:'
  ? 'http://127.0.0.1:5100/api/v1'
  : '/api/v1';

const TOKEN_KEY = 'godfin_auth_token';

export class ApiError extends Error {
  constructor({
    code,
    message,
    hint = null,
    retriable = false,
    status = 0,
    retryAfter = 0,
  }) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.hint = hint;
    this.retriable = retriable;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setStoredToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

let _token = getStoredToken();

export function setAuthToken(token) {
  _token = token;
  setStoredToken(token);
}

export function getAuthToken() {
  return _token;
}

export async function apiFetch(path, options = {}) {
  const {
    auth = true,
    responseType = 'json',
    headers: providedHeaders,
    ...fetchOptions
  } = options;
  const headers = new Headers(providedHeaders || {});
  const isFormData = fetchOptions.body instanceof FormData;

  if (!isFormData && fetchOptions.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (auth && _token) {
    headers.set('Authorization', `Bearer ${_token}`);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers,
    });
  } catch {
    throw new ApiError({
      code: 'NETWORK_ERROR',
      message: 'GODFIN cannot reach its local backend.',
      hint: 'Make sure GODFIN is running, then try again.',
      retriable: true,
    });
  }

  if (response.status === 401 && auth && !path.startsWith('/auth/')) {
    setAuthToken(null);
    if (window.location.pathname !== '/pin') {
      window.location.assign('/pin');
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const retryAfter = Number.parseInt(response.headers.get('Retry-After') || '0', 10);
    throw new ApiError({
      code: body.code || `HTTP_${response.status}`,
      message: body.message || body.detail || `Request failed (${response.status})`,
      hint: body.hint || null,
      retriable: body.retriable ?? response.status >= 500,
      status: response.status,
      retryAfter: Number.isFinite(retryAfter) ? Math.max(0, retryAfter) : 0,
    });
  }

  if (response.status === 204) return null;
  if (responseType === 'blob') return response.blob();
  if (responseType === 'text') return response.text();
  return response.json();
}

// Health
export async function fetchHealth(options = {}) {
  return apiFetch('/health', { ...options, auth: false });
}

// Auth
export function fetchAuthStatus() {
  return apiFetch('/auth/status', { auth: false });
}

export function setPin(pin) {
  return apiFetch('/auth/set-pin', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  });
}

export function verifyPin(pin) {
  return apiFetch('/auth/verify-pin', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  });
}

export function changePin(currentPin, newPin) {
  return apiFetch('/auth/change-pin', {
    method: 'POST',
    body: JSON.stringify({ current_pin: currentPin, new_pin: newPin }),
  });
}

export function logoutSession() {
  return apiFetch('/auth/logout', { method: 'POST' });
}

// LLM
export function fetchLLMConfig() {
  return apiFetch('/llm/config');
}

export function fetchLLMProviders() {
  return apiFetch('/llm/providers');
}

export function createLLMConfig(data) {
  return apiFetch('/llm/config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateLLMConfig(id, data) {
  return apiFetch(`/llm/config/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteLLMConfig(id) {
  return apiFetch(`/llm/config/${id}`, { method: 'DELETE' });
}

export function testLLMConnection(data) {
  return apiFetch('/llm/config/test', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function activateLLMConfig(id) {
  return apiFetch(`/llm/config/activate/${id}`, { method: 'POST' });
}

// Transactions
export function createTransaction(data) {
  return apiFetch('/transactions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function fetchTransactions(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') query.set(k, v);
  });
  const qs = query.toString();
  return apiFetch(`/transactions${qs ? `?${qs}` : ''}`);
}

export function fetchTransaction(id) {
  return apiFetch(`/transactions/${id}`);
}

export function updateTransaction(id, data) {
  return apiFetch(`/transactions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteTransaction(id) {
  return apiFetch(`/transactions/${id}`, {
    method: 'DELETE',
  });
}

// Dashboard
export function fetchDashboardStats(month, period = 'full') {
  return apiFetch(`/dashboard/stats?month=${month}&period=${period}`);
}

export function fetchDashboardMonths() {
  return apiFetch('/dashboard/months');
}

// Accounts
export function fetchAccounts() {
  return apiFetch('/accounts');
}

export function fetchAllAccounts() {
  return apiFetch('/accounts?include_inactive=true');
}

export function createAccount(data) {
  return apiFetch('/accounts', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateAccount(id, data) {
  return apiFetch(`/accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export function deactivateAccount(id) {
  return apiFetch(`/accounts/${id}`, { method: 'DELETE' });
}

export function fetchParserProfiles() {
  return apiFetch('/accounts/parser-profiles');
}

export function fetchSenderMappings() {
  return apiFetch('/accounts/sender-mappings');
}

export function replaceSenderMappings(mappings) {
  return apiFetch('/accounts/sender-mappings', {
    method: 'PUT',
    body: JSON.stringify({ mappings }),
  });
}

// Dashboard charts
export function fetchCategoryBreakdown(month, period = 'full') {
  return apiFetch(`/dashboard/category-breakdown?month=${month}&period=${period}`);
}

export function fetchSpendingTrend(months = 6, month = null) {
  const params = [`months=${months}`];
  if (month) params.push(`month=${month}`);
  return apiFetch(`/dashboard/spending-trend?${params.join('&')}`);
}

export function fetchSpendingTrends(month) {
  return apiFetch(`/dashboard/trends?month=${month}`);
}

export function fetchSpendingTrendsWithCategories(month) {
  return apiFetch(`/dashboard/trends/categories?month=${month}`);
}

// Review Queue
export function fetchReviewQueue(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') query.set(k, v);
  });
  const qs = query.toString();
  return apiFetch(`/review${qs ? `?${qs}` : ''}`);
}

export function resolveReview(id, data) {
  return apiFetch(`/review/${id}/resolve`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function resolveReviewItem(transactionId, category, subcategory = null) {
  return apiFetch(`/review/${transactionId}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ category, subcategory }),
  });
}

export function batchResolve(items) {
  return apiFetch('/review/batch-resolve', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
}

export function fetchReviewStats() {
  return apiFetch('/review/stats');
}

export function fetchCategories() {
  return fetchTaxonomy().then(({ categories }) =>
    Object.fromEntries(
      Object.entries(categories).map(([category, data]) => [
        category,
        data.subcategories,
      ]),
    )
  );
}

export function fetchTaxonomy() {
  return apiFetch('/taxonomy');
}

// Gmail / Ingestion
export function fetchGmailAuthUrl() {
  return apiFetch('/auth/gmail/url');
}

export function fetchGmailStatus() {
  return apiFetch('/auth/gmail/status');
}

export function disconnectGmail({ clearData = false, pin = null, confirmation = null } = {}) {
  return apiFetch('/auth/gmail/disconnect', {
    method: 'POST',
    body: JSON.stringify({
      clear_data: clearData,
      pin,
      confirmation,
    }),
  });
}

export function triggerIngestionWithDates({ startDate, endDate }) {
  return apiFetch('/ingest/gmail/range', {
    method: 'POST',
    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
  });
}

export function fetchIngestionStatus() {
  return apiFetch('/ingest/status');
}

export function fetchSchedulerStatus() {
  return apiFetch('/ingest/scheduler/status');
}

export function fetchIngestSettings() {
  return apiFetch('/ingest/settings');
}

export function updateIngestSettings(enabled, frequencyMinutes = 15) {
  return apiFetch('/ingest/settings', {
    method: 'POST',
    body: JSON.stringify({ enabled, frequency_minutes: frequencyMinutes }),
  });
}

export function triggerIngestion() {
  return apiFetch('/ingest/gmail', { method: 'POST' });
}

export function triggerGmailIngest(maxResults = 100) {
  return apiFetch(`/ingest/gmail?max_results=${maxResults}`, { method: 'POST' });
}

export function triggerInitialIngest() {
  return apiFetch('/ingest/gmail/initial', { method: 'POST' });
}

export function startInitialSync() {
  return apiFetch('/ingest/gmail/initial/start', { method: 'POST' });
}

export function fetchSyncStatus() {
  return apiFetch('/ingest/gmail/sync-status');
}

export function startIngestionWithDates({ startDate, endDate }) {
  return apiFetch('/ingest/gmail/range/start', { method: 'POST', body: JSON.stringify({ start_date: startDate, end_date: endDate }) });
}

export function fetchIngestionProgress() {
  return apiFetch('/ingest/gmail/range/status');
}

// Statement Upload - GLM multi-step flow
export async function previewStatement(file, password = null) {
  const formData = new FormData();
  formData.append('file', file);
  if (password) formData.append('password', password);

  return apiFetch('/ingest/upload/preview', {
    method: 'POST',
    body: formData,
  });
}

export async function reconcileStatement(file, accountId, password = null) {
  const formData = new FormData();
  formData.append('file', file);
  if (accountId) formData.append('account_id', accountId);
  if (password) formData.append('password', password);

  return apiFetch('/ingest/upload/reconcile', {
    method: 'POST',
    body: formData,
  });
}

export async function importStatement(file, accountId, options = {}) {
  const formData = new FormData();
  formData.append('file', file);
  if (accountId) formData.append('account_id', accountId);
  if (options.password) formData.append('password', options.password);
  formData.append('import_new', options.importNew !== false);
  formData.append('detect_income', options.detectIncome !== false);
  formData.append('confirm_reconciled', options.confirmReconciled === true);
  if (options.acceptedFingerprint) {
    formData.append('accepted_fingerprint', options.acceptedFingerprint);
  }

  return apiFetch('/ingest/upload/import', {
    method: 'POST',
    body: formData,
  });
}

// Legacy upload (backward compat)
export async function uploadStatement(file, password) {
  return previewStatement(file, password);
}

// Income Sources
export function fetchIncomeSources(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') query.set(k, v);
  });
  const qs = query.toString();
  return apiFetch(`/income${qs ? `?${qs}` : ''}`);
}

export function fetchIncomeSource(id) {
  return apiFetch(`/income/${id}`);
}

export function createIncomeSource(data) {
  return apiFetch('/income', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateIncomeSource(id, data) {
  return apiFetch(`/income/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteIncomeSource(id) {
  return apiFetch(`/income/${id}`, { method: 'DELETE' });
}

export function fetchIncomeStats(month) {
  return apiFetch(`/income/stats?month=${month}`);
}

// Goals
export function fetchGoals() {
  return apiFetch('/goals');
}

export function createGoal(data) {
  return apiFetch('/goals', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateGoal(id, data) {
  return apiFetch(`/goals/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteGoal(id) {
  return apiFetch(`/goals/${id}`, { method: 'DELETE' });
}

export function simulateGoal(id) {
  return apiFetch(`/goals/${id}/simulate`, { method: 'POST' });
}

export function fetchGoalContributions(id, includeVoided = false) {
  return apiFetch(
    `/goals/${id}/contributions?include_voided=${includeVoided}`
  );
}

export function createGoalContribution(id, data) {
  return apiFetch(`/goals/${id}/contributions`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function voidGoalContribution(goalId, contributionId, reason) {
  return apiFetch(`/goals/${goalId}/contributions/${contributionId}/void`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export function fetchGoalContributionSuggestions() {
  return apiFetch('/goal-contribution-suggestions');
}

export function decideGoalContributionSuggestion(suggestionId, goalId) {
  return apiFetch(
    `/goal-contribution-suggestions/${suggestionId}/decision`,
    {
      method: 'POST',
      body: JSON.stringify({ goal_id: goalId || null }),
    }
  );
}

// Recurring
export function fetchRecurring() {
  return apiFetch('/recurring');
}

export function detectRecurring() {
  return apiFetch('/recurring/detect', { method: 'POST' });
}

// Financial Profile
export function fetchFinancialProfile() {
  return apiFetch('/profile');
}

// Cash flow
export function fetchCashFlowCalendar(month) {
  const qs = month ? `?month=${encodeURIComponent(month)}` : '';
  return apiFetch(`/cash-flow/calendar${qs}`);
}

// Transfer matching
export function fetchTransferMatches(includeResolved = false) {
  return apiFetch(`/transfers?include_resolved=${includeResolved}`);
}

export function scanTransferMatches() {
  return apiFetch('/transfers/scan', { method: 'POST' });
}

export function decideTransferMatch({ id, decision, snoozeDays = 7, note = null }) {
  return apiFetch(`/transfers/${id}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      decision,
      snooze_days: snoozeDays,
      note,
    }),
  });
}

// Elasticity
export function fetchElasticity() {
  return apiFetch('/elasticity');
}

// Reports
export function fetchReportSummary(month) {
  const qs = month ? `?month=${month}` : '';
  return apiFetch(`/reports/summary${qs}`);
}

export function fetchReportDetailed(month) {
  const qs = month ? `?month=${month}` : '';
  return apiFetch(`/reports/detailed${qs}`);
}

export function updateReportSavingsTarget(targetPercent) {
  return apiFetch('/reports/preferences/savings-target', {
    method: 'PUT',
    body: JSON.stringify({ target_percent: targetPercent }),
  });
}

export function generateReportInsights(month) {
  return apiFetch('/reports/ai/insights', {
    method: 'POST',
    body: JSON.stringify({ month: month || null, consent: true }),
  });
}

export function fetchReportTransactions(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') query.set(k, v);
  });
  const qs = query.toString();
  return apiFetch(`/reports/transactions${qs ? `?${qs}` : ''}`);
}

export function fetchMonthlyComparison(months = 6) {
  return apiFetch(`/reports/comparison?months=${months}`);
}

export function downloadReportPDF(startDate, endDate, includeCommentary = false) {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  if (includeCommentary) params.set('include_commentary', 'true');
  const qs = params.toString();
  return `${API_BASE}/reports/pdf${qs ? `?${qs}` : ''}`;
}

// Audit
export function startAudit(year, month) {
  return apiFetch('/audit/start', {
    method: 'POST',
    body: JSON.stringify({ year, month }),
  });
}

export function fetchAuditSessions(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) query.set(k, String(v));
  });
  const qs = query.toString();
  return apiFetch(`/audit/sessions${qs ? `?${qs}` : ''}`);
}

export function fetchAuditSession(id) {
  return apiFetch(`/audit/sessions/${id}`);
}

export function finalizeAudit(id) {
  return apiFetch(`/audit/${id}/finalize`, { method: 'POST' });
}

export function discardAudit(id) {
  return apiFetch(`/audit/${id}/discard`, { method: 'POST' });
}

export function reopenAudit(id) {
  return apiFetch(`/audit/${id}/reopen`, { method: 'POST' });
}

export function fetchMonthStatus(year, month) {
  return apiFetch(`/audit/month-status?year=${year}&month=${month}`);
}

// Settings
export function fetchSettings() {
  return apiFetch('/settings');
}

export function fetchSettingsHealth() {
  return apiFetch('/settings/health');
}

export function updateTimezone(timezone) {
  return apiFetch('/settings/preferences/timezone', {
    method: 'PUT',
    body: JSON.stringify({ timezone }),
  });
}

export function updateNetworkAccess(enabled, currentPin = null) {
  return apiFetch('/settings/preferences/network-access', {
    method: 'PUT',
    body: JSON.stringify({ enabled, current_pin: currentPin }),
  });
}

export function updateDeveloperMode(enabled, currentPin = null) {
  return apiFetch('/settings/preferences/developer-mode', {
    method: 'PUT',
    body: JSON.stringify({ enabled, current_pin: currentPin }),
  });
}

export function triggerBackup() {
  return apiFetch('/settings/backup', { method: 'POST' });
}

export function fetchBackups() {
  return apiFetch('/settings/backups');
}

export function fetchDeveloperMode() {
  return apiFetch('/settings/developer');
}

export function createRule(data) {
  return apiFetch('/settings/developer/rules', { method: 'POST', body: JSON.stringify(data) });
}

export function updateRule({ id, ...data }) {
  return apiFetch(`/settings/developer/rules/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}

export function deleteRule(id) {
  return apiFetch(`/settings/developer/rules/${id}`, { method: 'DELETE' });
}

export function resetData(pin, createBackup = true) {
  return apiFetch('/settings/reset-data', {
    method: 'POST',
    body: JSON.stringify({ pin, create_backup: createBackup }),
  });
}

// License
export function fetchLicenseStatus() {
  return apiFetch('/license');
}

export function activateLicense(licenseKey) {
  return apiFetch('/license/activate', {
    method: 'POST',
    body: JSON.stringify({ license_key: licenseKey }),
  });
}

export function verifyLicense() {
  return apiFetch('/license/verify', { method: 'POST' });
}

export function deactivateLicense() {
  return apiFetch('/license', { method: 'DELETE' });
}

// Subscriptions
export function fetchSubscriptions(params) {
  const q = new URLSearchParams();
  if (params?.is_active != null) q.set('is_active', params.is_active);
  return apiFetch(`/subscriptions${q.toString() ? '?' + q : ''}`);
}

export function createSubscription(data) {
  return apiFetch('/subscriptions', { method: 'POST', body: JSON.stringify(data) });
}

export function updateSubscription({ id, ...data }) {
  return apiFetch(`/subscriptions/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}

export function deleteSubscription(id) {
  return apiFetch(`/subscriptions/${id}`, { method: 'DELETE' });
}

export function fetchSubscriptionStats() {
  return apiFetch('/subscriptions/stats');
}

export function fetchExchangeRates() {
  return apiFetch('/subscriptions/exchange-rates');
}

export function refreshExchangeRates() {
  return apiFetch('/subscriptions/exchange-rates/refresh', { method: 'POST' });
}

export function scanSubscriptionSuggestions() {
  return apiFetch('/subscriptions/suggestions/scan', { method: 'POST' });
}

export function fetchSubscriptionSuggestions(includeResolved = false) {
  return apiFetch(`/subscriptions/suggestions?include_resolved=${includeResolved}`);
}

export function decideSubscriptionSuggestion({ id, decision, snoozeDays = 7 }) {
  return apiFetch(`/subscriptions/suggestions/${id}/decision`, {
    method: 'POST',
    body: JSON.stringify({ decision, snooze_days: snoozeDays }),
  });
}

export function fetchSubscriptionReminders(days = 7) {
  return apiFetch(`/subscriptions/reminders?days=${days}`);
}

// Advisor
export function sendAdvisorChat({ message, history }) {
  return apiFetch('/advisor/chat', { method: 'POST', body: JSON.stringify({ message, history }) });
}

export function fetchAdvisorDigest() {
  return apiFetch('/advisor/digest');
}

export function fetchAdvisorDigestSettings() {
  return apiFetch('/advisor/digest/settings');
}

export function updateAdvisorDigestSettings(data) {
  return apiFetch('/advisor/digest/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function sendAdvisorDigest() {
  return apiFetch('/advisor/digest/send', { method: 'POST' });
}

export function sendReviewChat({ transactionId, message, history }) {
  return apiFetch(`/review/${transactionId}/chat`, { method: 'POST', body: JSON.stringify({ message, history }) });
}

// System
export function fetchSystemStatus() {
  return apiFetch('/system/status');
}

export function restartBackend() {
  return apiFetch('/system/restart', { method: 'POST' });
}

export function fetchEmbeddingStatus() {
  return apiFetch('/system/embeddings/status');
}

export function enableEmbeddings() {
  return apiFetch('/system/embeddings/enable', { method: 'POST' });
}

export function fetchFeatureFlags() {
  return apiFetch('/system/feature-flags');
}

// Max net worth
export function fetchNetWorth() {
  return apiFetch('/net-worth');
}

export function createNetWorthItem(data) {
  return apiFetch('/net-worth', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateNetWorthItem({ id, ...data }) {
  return apiFetch(`/net-worth/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function deleteNetWorthItem(id) {
  return apiFetch(`/net-worth/${id}`, { method: 'DELETE' });
}

export function refreshNetWorthQuote(id) {
  return apiFetch(`/net-worth/${id}/refresh`, { method: 'POST' });
}

export function fetchMarketDataStatus() {
  return apiFetch('/net-worth/market-data/config/status');
}

export function configureMarketData(data) {
  return apiFetch('/net-worth/market-data/config', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// Transparent behavior insights
export function fetchBehaviorInsights() {
  return apiFetch('/behavior-insights');
}

export function updateBehaviorConfig(monthlyBudget) {
  return apiFetch('/behavior-insights/config', {
    method: 'PUT',
    body: JSON.stringify({ monthly_budget: monthlyBudget }),
  });
}

export function updateBehaviorPreference(metricKey, data) {
  return apiFetch(`/behavior-insights/${metricKey}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export function resetBehaviorInsights() {
  return apiFetch('/behavior-insights/reset', { method: 'POST' });
}

export function fetchSponsorCard() {
  return apiFetch('/behavior-insights/sponsor/card');
}

export async function downloadBehaviorInsights() {
  const blob = await apiFetch('/behavior-insights/export', { responseType: 'blob' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'godfin-behavior-insights.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

// Separately consented compensated-data pilot
export function fetchRewardPilotStatus() {
  return apiFetch('/reward-pilot/status');
}

export function updateRewardPilotConsent(consented) {
  return apiFetch('/reward-pilot/consent', {
    method: 'PUT',
    body: JSON.stringify({ consented }),
  });
}

export function fetchRewardPilotPreview() {
  return apiFetch('/reward-pilot/preview');
}

export function submitRewardPilotBundle() {
  return apiFetch('/reward-pilot/submit', { method: 'POST' });
}

// CSV Export
export async function downloadCSV(month) {
  const qs = month ? `?month=${month}` : '';
  const blob = await apiFetch(`/reports/csv${qs}`, { responseType: 'blob' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `godfin_transactions_${month || 'all'}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadMonthlyReportPDF(type, month) {
  const qs = month ? `?month=${month}` : '';
  const blob = await apiFetch(
    type === 'detailed' ? '/reports/pdf/detailed' : `/reports/pdf/${type}${qs}`,
    type === 'detailed'
      ? {
          method: 'POST',
          body: JSON.stringify({ month: month || null, consent: true }),
          responseType: 'blob',
        }
      : { responseType: 'blob' },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `godfin_${type}_${month}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadFinancialYear(startYear, format = 'csv') {
  const blob = await apiFetch(
    `/reports/fy?start_year=${startYear}&format=${format}`,
    { responseType: 'blob' },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `godfin_ca_fy${startYear}-${String(startYear + 1).slice(-2)}.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadFinancialYearPack(startYear, passphrase) {
  const blob = await apiFetch(
    '/reports/fy/pack',
    {
      method: 'POST',
      body: JSON.stringify({ start_year: startYear, passphrase }),
      responseType: 'blob',
    },
  );
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `godfin_ca_tax_pack_fy${startYear}-${String(startYear + 1).slice(-2)}.zip`;
  anchor.click();
  URL.revokeObjectURL(url);
}

// Onboarding
export function fetchOnboardingStatus() {
  return apiFetch('/onboarding');
}

export function updateOnboardingStatus(data) {
  return apiFetch('/onboarding', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// Guided local AI
export function fetchLocalAIProfile() {
  return apiFetch('/system/local-ai/profile');
}

export function chooseLocalAI(choice) {
  return apiFetch('/system/local-ai/choice', {
    method: 'PUT',
    body: JSON.stringify({ choice }),
  });
}

export function fetchLocalAIDownload() {
  return apiFetch('/system/local-ai/download');
}

export function downloadLocalAIModel(model) {
  return apiFetch('/system/local-ai/download', {
    method: 'POST',
    body: JSON.stringify({ model, confirmed: true }),
  });
}

export function cancelLocalAIDownload() {
  return apiFetch('/system/local-ai/download/cancel', { method: 'POST' });
}

export function benchmarkLocalAI(model) {
  return apiFetch('/system/local-ai/benchmark', {
    method: 'POST',
    body: JSON.stringify({ model, confirmed: true }),
  });
}

export function fetchClassificationMemory(limit = 100) {
  return apiFetch(`/settings/classification-memory?limit=${limit}`);
}

export function undoClassificationCorrection(correctionId) {
  return apiFetch(`/settings/classification-memory/${correctionId}/undo`, {
    method: 'POST',
  });
}

export function updatePersonalClassifier(enabled) {
  return apiFetch('/settings/classification-memory/personal', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  });
}

export function resetClassificationMemory(pin) {
  return apiFetch('/settings/classification-memory/reset', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  });
}

export async function downloadClassificationMemory() {
  const blob = await apiFetch('/settings/classification-memory/export', {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'godfin-classification-memory.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

export const authApi = {
  status: fetchAuthStatus,
  setPin,
  verifyPin,
  changePin,
  logout: logoutSession,
};

export const transactionsApi = {
  list: fetchTransactions,
  get: fetchTransaction,
  create: createTransaction,
  update: updateTransaction,
  remove: deleteTransaction,
};

export const dashboardApi = {
  stats: fetchDashboardStats,
  months: fetchDashboardMonths,
  categoryBreakdown: fetchCategoryBreakdown,
  spendingTrend: fetchSpendingTrend,
};

export const accountsApi = {
  list: fetchAccounts,
  listAll: fetchAllAccounts,
  create: createAccount,
  update: updateAccount,
  deactivate: deactivateAccount,
  parserProfiles: fetchParserProfiles,
  senderMappings: fetchSenderMappings,
  replaceSenderMappings,
};

export const taxonomyApi = {
  get: fetchTaxonomy,
};

export const auditApi = {
  start: startAudit,
  list: fetchAuditSessions,
  get: fetchAuditSession,
  finalize: finalizeAudit,
  discard: discardAudit,
  reopen: reopenAudit,
  monthStatus: fetchMonthStatus,
};

export const reportsApi = {
  summary: fetchReportSummary,
  detailed: fetchReportDetailed,
  updateSavingsTarget: updateReportSavingsTarget,
  generateInsights: generateReportInsights,
  transactions: fetchReportTransactions,
  comparison: fetchMonthlyComparison,
  downloadCSV,
  downloadMonthlyReportPDF,
  downloadFinancialYear,
};

export const settingsApi = {
  get: fetchSettings,
  health: fetchSettingsHealth,
  updateTimezone,
  updateNetworkAccess,
  updateDeveloperMode,
  backup: triggerBackup,
  backups: fetchBackups,
  developer: fetchDeveloperMode,
  embeddingStatus: fetchEmbeddingStatus,
  enableEmbeddings,
  classificationMemory: fetchClassificationMemory,
  undoClassificationCorrection,
  updatePersonalClassifier,
  resetClassificationMemory,
  downloadClassificationMemory,
};

export const localAIApi = {
  profile: fetchLocalAIProfile,
  choose: chooseLocalAI,
  downloadStatus: fetchLocalAIDownload,
  download: downloadLocalAIModel,
  cancelDownload: cancelLocalAIDownload,
  benchmark: benchmarkLocalAI,
};

export const licenseApi = {
  status: fetchLicenseStatus,
  activate: activateLicense,
  verify: verifyLicense,
  deactivate: deactivateLicense,
};
