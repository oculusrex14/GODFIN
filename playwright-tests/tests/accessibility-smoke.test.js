const { test, expect } = require('@playwright/test');

test.use({
  viewport: { width: 390, height: 844 },
  hasTouch: true,
  isMobile: true,
});

async function mockIsolatedAccessibilityApp(page) {
  let onboarding = {
    completed: false,
    deferred: false,
    step: 1,
    step_count: 6,
    tutorial_version: 1,
    tutorial_step: 1,
    tutorial_step_count: 10,
    tutorial_completed: false,
    tutorial_completed_version: 0,
    tutorial_update_available: false,
    transaction_count: 0,
    reviewed_count: 0,
    target_review_count: 0,
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.slice('/api/v1'.length);
    if (path === '/health') return route.fulfill({ json: { status: 'ok' } });
    if (path === '/auth/status') {
      return route.fulfill({ json: { is_first_run: true, pin_length: null } });
    }
    if (path === '/auth/set-pin') {
      return route.fulfill({ json: { authenticated: true, token: 'isolated-test-token' } });
    }
    if (path === '/onboarding' && request.method() === 'PUT') {
      onboarding = { ...onboarding, ...request.postDataJSON() };
      return route.fulfill({ json: onboarding });
    }
    const responses = {
      '/onboarding': onboarding,
      '/audit/sessions': [],
      '/review/stats': { queue_size: 0 },
      '/ingest/gmail/sync-status': { status: 'idle', percent: 0 },
      '/settings': { theme: 'dark', allow_network_access: 'false' },
      '/settings/health': {
        gmail: { status: 'not_configured' },
        llm: { status: 'not_configured' },
        backup: { status: 'healthy' },
        license: { status: 'inactive' },
      },
      '/settings/developer': { enabled: false, rules: [] },
      '/settings/backups': [],
      '/system/embeddings/status': { status: 'not_installed' },
      '/system/local-ai/profile': {
        choice: 'none',
        ollama: { installed: false },
        recommendations: [],
      },
      '/system/local-ai/download': { status: 'idle' },
      '/accounts': [],
      '/accounts/parser-profiles': [],
      '/accounts/sender-mappings': [],
      '/auth/gmail/status': { connected: false, status: 'not_configured' },
      '/license': { tier: 'free', valid: false, status: 'inactive', features: [] },
      '/llm/config': null,
      '/settings/classification-memory': {
        corrections: [],
        total_confirmed: 0,
        personal_classifier: { enabled: false, eligible: false },
      },
      '/reward-pilot/status': { consented: false, enabled: false },
    };
    return route.fulfill({ json: responses[path] ?? {} });
  });
}

test('PIN and beginner tutorial support keyboard, touch, and accessible names', async ({ page }) => {
  await mockIsolatedAccessibilityApp(page);
  await page.goto('/pin');
  const pinInput = page.locator('input[type="password"]');
  await expect(pinInput).toHaveCount(1);
  await expect(pinInput).toHaveAttribute('aria-describedby', 'pin-length-hint');
  await expect(page.locator('#pin-length-hint')).toBeVisible();

  const submit = page.getByRole('button', { name: /Set PIN|Unlock/ });
  const inputBox = await pinInput.boundingBox();
  const buttonBox = await submit.boundingBox();
  expect(inputBox.height).toBeGreaterThanOrEqual(44);
  expect(buttonBox.height).toBeGreaterThanOrEqual(44);

  await expect(pinInput).toBeFocused();
  await pinInput.fill('2468');
  await page.keyboard.press('Tab');
  await expect(submit).toBeFocused();
  await page.keyboard.press('Enter');

  const onboardingHeading = page.getByRole('heading', { name: 'Make GODFIN yours' });
  const dashboardHeading = page.getByRole('heading', { name: 'Dashboard' });
  await expect(onboardingHeading.or(dashboardHeading)).toBeVisible();
  if (await onboardingHeading.isVisible()) {
    await page.getByRole('button', { name: 'Finish setup later' }).click();
  }
  await expect(dashboardHeading).toBeVisible();

  await page.getByRole('button', { name: 'Open navigation menu' }).click();
  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  const learningSection = page.getByRole('button', { name: 'Setup & Learning' });
  await expect(learningSection).toHaveAttribute('aria-expanded', 'false');
  await learningSection.click();
  await expect(learningSection).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('button', { name: 'Learn GODFIN' }).click();
  await expect(
    page.getByRole('heading', { name: 'Finance basics, one calm step at a time' }),
  ).toBeVisible();

  await expect(page.getByLabel('Lesson 1 of 10')).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByLabel('Lesson 2 of 10')).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByLabel('Lesson 1 of 10')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});
