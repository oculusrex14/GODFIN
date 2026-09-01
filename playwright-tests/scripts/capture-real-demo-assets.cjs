'use strict';

const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { mkdir, readFile, writeFile } = require('node:fs/promises');
const { chromium } = require('@playwright/test');

// Capture only the compiled exact-app demo. Its own in-memory transport is the
// canonical public fixture, so this script deliberately contains no duplicate
// API responses that could drift away from what visitors actually see.
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
const FIXED_NOW_ISO = '2026-07-31T12:00:00+05:30';

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

async function stabilizePage(page) {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addStyleTag({ content: DETERMINISTIC_STYLE });
  await page.addStyleTag({ content: '.godfin-demo-badge { display: none !important; }' });
  await page.evaluate(() => document.activeElement?.blur());
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
  });
  await page.waitForTimeout(1800);
  await page.evaluate(() => document.activeElement?.blur());
}

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

function findSensitiveVisibleText(value) {
  const findings = [];
  findings.push(
    ...[...value.matchAll(EMAIL_PATTERN)]
      .map(([match]) => match)
      .filter((match) => match.toLowerCase() !== 'hello@godfin.dev')
      .map((match) => `email:${match}`),
  );
  for (const [label, pattern] of [
    ['phone', PHONE_PATTERN],
    ['phone', GROUPED_PHONE_PATTERN],
    ['upi', UPI_PATTERN],
    ['ifsc', IFSC_PATTERN],
    ['license', LICENSE_PATTERN],
    ['license', LICENSE_LABEL_PATTERN],
    ['account', LONG_ACCOUNT_PATTERN],
    ['account', LABELED_ACCOUNT_PATTERN],
  ]) {
    findings.push(...[...value.matchAll(pattern)].map(([match]) => `${label}:${match}`));
  }
  return uniqueMatches(findings);
}

async function assertPublicSafe(page, routeName) {
  const findings = findSensitiveVisibleText(await page.locator('body').innerText());
  if (findings.length > 0) {
    throw new Error(`Sensitive-looking visible text on ${routeName}: ${findings.join(', ')}`);
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
  await page.getByRole('heading', { name: target.heading, exact: true }).waitFor({ state: 'visible' });
  await page.getByText(target.content, { exact: false }).first().waitFor({ state: 'visible' });
  await page.getByRole('main').waitFor({ state: 'visible' });
}

async function navigateTo(page, target) {
  const link = page.getByRole('link', { name: target.nav, exact: true });
  await link.waitFor({ state: 'visible' });
  await link.click();
  await page.waitForFunction((expectedRoute) => {
    const pathname = window.location.pathname;
    if (expectedRoute === '/') return /\/demo-app(?:\/index\.html)?\/?$/.test(pathname);
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
  return execFileSync('git', ['-C', repositoryRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
}

async function openDemo(context) {
  const page = await context.newPage();
  const forbiddenRequests = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin !== new URL(baseUrl).origin || url.pathname.includes('/api/v1/')) {
      forbiddenRequests.push(request.url());
    }
  });
  await page.goto(`${baseUrl}/demo`, { waitUntil: 'domcontentloaded' });
  await waitForRoute(page, routes[0]);
  if (forbiddenRequests.length > 0) {
    throw new Error(`The public demo made forbidden requests: ${forbiddenRequests.join(', ')}`);
  }
  return page;
}

async function main() {
  await mkdir(outputDirectory, { recursive: true });
  const fixtureBytes = await readFile(goldenFixturePath);
  const gitSha = sourceGitSha();
  const fixtureSha256 = createHash('sha256').update(fixtureBytes).digest('hex');
  const browser = await chromium.launch({ headless: true });
  const captures = [];
  try {
    const dashboardContext = await browser.newContext({
      viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2,
      locale: 'en-IN', timezoneId: 'Asia/Kolkata', colorScheme: 'dark', reducedMotion: 'reduce',
    });
    const dashboardPage = await openDemo(dashboardContext);
    const dashboardPath = path.join(outputDirectory, 'godfin-dashboard-synthetic-2x.png');
    await captureScreenshot(dashboardPage, routes[0], dashboardPath, { width: 2880, height: 1800 });
    captures.push({
      route: '/', heading: 'Dashboard', filename: 'godfin-dashboard-synthetic-2x.png',
      viewport: { width: 1440, height: 900, device_scale_factor: 2 },
      dimensions: { width: 2880, height: 1800 },
    });
    await dashboardContext.close();

    const standardContext = await browser.newContext({
      viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1,
      locale: 'en-IN', timezoneId: 'Asia/Kolkata', colorScheme: 'dark', reducedMotion: 'reduce',
    });
    const page = await openDemo(standardContext);
    for (const target of routes) {
      if (target.route !== '/') await navigateTo(page, target);
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
