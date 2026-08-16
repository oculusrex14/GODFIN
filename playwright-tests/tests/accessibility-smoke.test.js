const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

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
    if (path === '/health') {
      return route.fulfill({
        json: { status: 'alive', liveness: true, database: 'not_checked', version: '0.1.0' },
      });
    }
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

async function expectNoSeriousAxeViolations(page, include) {
  let builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']);
  if (include) builder = builder.include(include);
  const result = await builder.analyze();
  const violations = result.violations.filter((item) => (
    item.impact === 'critical' || item.impact === 'serious'
  ));
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
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
  const settingsHeading = page.getByRole('heading', { name: 'Settings', exact: true });
  await expect(settingsHeading).toBeVisible();
  await expect(settingsHeading).toBeFocused();
  await expectNoSeriousAxeViolations(page, '#main-content');

  const skipLink = page.getByRole('link', { name: 'Skip to main content' });
  await skipLink.focus();
  await expect(skipLink).toBeFocused();
  await skipLink.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();

  const dataSection = page.getByRole('button', { name: 'Data Management' });
  await dataSection.click();
  const resetTrigger = page.getByRole('button', { name: 'Reset Data' });
  await resetTrigger.click();
  const dialog = page.getByRole('dialog', { name: 'Reset All Data?' });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeFocused();
  expect(await page.locator('[inert]').count()).toBeGreaterThan(0);

  const dialogButtons = dialog.getByRole('button');
  const firstDialogButton = dialogButtons.first();
  const lastDialogButton = dialogButtons.last();
  await lastDialogButton.focus();
  await page.keyboard.press('Tab');
  await expect(firstDialogButton).toBeFocused();
  await firstDialogButton.focus();
  await page.keyboard.press('Shift+Tab');
  await expect(lastDialogButton).toBeFocused();
  await expectNoSeriousAxeViolations(page, '[data-godfin-dialog="true"]');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(resetTrigger).toBeFocused();

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

test('app keeps essential content available at 400% text scaling and reduced motion', async ({ page }) => {
  await mockIsolatedAccessibilityApp(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/pin');
  await page.locator('input[type="password"]').fill('2468');
  await page.getByRole('button', { name: /Set PIN|Unlock/ }).click();
  const onboardingHeading = page.getByRole('heading', { name: 'Make GODFIN yours' });
  if (await onboardingHeading.isVisible()) {
    await page.getByRole('button', { name: 'Finish setup later' }).click();
  }
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '400%';
  });
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open navigation menu' })).toBeVisible();
  const transitionDuration = await page.getByRole('button', { name: 'Open navigation menu' }).evaluate(
    (element) => getComputedStyle(element).transitionDuration,
  );
  expect(['0s', '0.00001s']).toContain(transitionDuration);
});
