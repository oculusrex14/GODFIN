const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');

const repoRoot = path.resolve(__dirname, '../..');
const statementPath = process.env.GODFIN_E2E_STATEMENT;
if (!statementPath) throw new Error('GODFIN_E2E_STATEMENT is required');

const websiteScreenshots = path.join(repoRoot, 'website/public/screenshots');
const privateArtifacts = path.join(repoRoot, 'docs/launch-artifacts');
fs.mkdirSync(websiteScreenshots, { recursive: true });
fs.mkdirSync(privateArtifacts, { recursive: true });

let activeBrowser;
let activeContext;

(async () => {
const browser = await chromium.launch({ headless: true });
activeBrowser = browser;
const context = await browser.newContext({
  baseURL: process.env.GODFIN_E2E_BASE_URL || 'http://127.0.0.1:5200',
  viewport: { width: 1244, height: 716 },
  recordVideo: {
    dir: privateArtifacts,
    size: { width: 1244, height: 716 },
  },
  colorScheme: 'dark',
});
activeContext = context;
const page = await context.newPage();
const video = page.video();

async function pause(milliseconds = 700) {
  await page.waitForTimeout(milliseconds);
}

async function screenshot(name, website = false) {
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
  await pause(120);
  const destination = website
    ? path.join(websiteScreenshots, `${name}.png`)
    : path.join(privateArtifacts, `${name}.png`);
  await page.screenshot({ path: destination, animations: 'disabled' });
}

async function api(pathname, options = {}) {
  return page.evaluate(async ({ pathname: endpoint, options: requestOptions }) => {
    const token = localStorage.getItem('godfin_auth_token');
    const response = await fetch(`/api/v1${endpoint}`, {
      ...requestOptions,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(requestOptions.headers || {}),
      },
    });
    const body = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      throw new Error(`${endpoint} failed (${response.status}): ${JSON.stringify(body)}`);
    }
    return body;
  }, { pathname, options });
}

await page.goto('/pin');
await page.getByLabel('Choose a 4 to 6 digit PIN').fill('2468');
await page.getByRole('button', { name: 'Set PIN' }).click();
await page.getByRole('button', { name: 'Finish setup later' }).click();

await page.getByRole('link', { name: 'Upload' }).click();
await page.locator('input[type="file"]').setInputFiles(path.resolve(statementPath));
await page.getByRole('button', { name: 'Upload & Reconcile' }).click();
const importButton = page.getByRole('button', { name: /Import \d+ New Transactions/ });
await importButton.waitFor();
await importButton.click();
await page.getByText('Import Complete').waitFor();
await pause();

await page.getByRole('link', { name: 'Dashboard' }).click();
await page.getByRole('heading', { name: 'Dashboard' }).waitFor();
await pause(900);
await screenshot('dashboard', true);

await page.getByRole('link', { name: 'Transactions', exact: true }).click();
await page.getByRole('heading', { name: 'Transactions', exact: true }).waitFor();
await pause();
await screenshot('transactions', true);

await page.getByRole('link', { name: 'Settings', exact: true }).click();
await page.getByRole('heading', { name: 'Settings', exact: true }).waitFor();
await page.getByRole('button', { name: 'Learn GODFIN' }).click();
await page.getByRole('heading', { name: 'Finance basics, one calm step at a time' }).waitFor();
await pause();
await screenshot('tutorial', true);
await page.getByRole('button', { name: 'Leave and resume later' }).click();
await page.getByRole('heading', { name: 'Dashboard' }).waitFor();

await page.getByRole('link', { name: 'Settings', exact: true }).click();
await page.getByRole('heading', { name: 'Settings', exact: true }).waitFor();
await page.getByLabel('Lifetime license key').fill(
  'GODFIN-MAX-ABCDE-FGHIJ-KLMNO-PQRST-UVWXY',
);
await page.getByRole('button', { name: 'Activate', exact: true }).click();
await page.getByText('GODFIN MAX', { exact: true }).waitFor();
await pause(4200);

const today = new Date();
const valuedAt = today.toISOString().slice(0, 10);
const expires = new Date(today);
expires.setDate(expires.getDate() + 90);
const expiresOn = expires.toISOString().slice(0, 10);

const items = [
  {
    name: 'Emergency fund',
    item_type: 'asset',
    asset_class: 'cash',
    valuation_mode: 'manual',
    currency: 'INR',
    manual_value: 240000,
    valuation_source: 'Synthetic bank balance',
    valued_at: valuedAt,
    expires_on: expiresOn,
  },
  {
    name: 'Long-term investments',
    item_type: 'asset',
    asset_class: 'stock',
    valuation_mode: 'manual',
    currency: 'INR',
    manual_value: 815000,
    valuation_source: 'Synthetic broker statement',
    valued_at: valuedAt,
    expires_on: expiresOn,
  },
  {
    name: 'Apartment estimate',
    item_type: 'asset',
    asset_class: 'property',
    valuation_mode: 'manual',
    currency: 'INR',
    manual_value: 6500000,
    valuation_source: 'Synthetic local valuation',
    valued_at: valuedAt,
    expires_on: expiresOn,
  },
  {
    name: 'Home loan',
    item_type: 'liability',
    asset_class: 'debt',
    valuation_mode: 'manual',
    currency: 'INR',
    manual_value: 725000,
    valuation_source: 'Synthetic loan statement',
    valued_at: valuedAt,
    expires_on: expiresOn,
  },
];
for (const item of items) {
  await api('/net-worth', { method: 'POST', body: JSON.stringify(item) });
}

await page.getByRole('link', { name: 'Net Worth', exact: true }).click();
await page.getByRole('heading', { name: 'Net Worth' }).waitFor();
await pause(1000);
await screenshot('net-worth');

await page.getByRole('link', { name: 'Behavior Insights', exact: true }).click();
await page.getByRole('heading', { name: 'Financial Behavior Insights' }).waitFor();
await pause(1000);
await screenshot('behavior-insights');

await page.getByRole('link', { name: 'Settings', exact: true }).click();
await page.getByRole('heading', { name: 'Settings', exact: true }).waitFor();
await pause(800);
await screenshot('settings-health');

await context.close();
activeContext = null;
await browser.close();
activeBrowser = null;

const rawVideo = await video.path();
const finalVideo = path.join(privateArtifacts, 'GODFIN_PRIVATE_DEMO.webm');
fs.copyFileSync(rawVideo, finalVideo);
if (rawVideo !== finalVideo) fs.rmSync(rawVideo);

console.log(`Captured privacy-safe launch screenshots in ${websiteScreenshots}.`);
console.log(`Captured private demo at ${finalVideo}.`);
})().catch(async (error) => {
  console.error(error);
  await activeContext?.close();
  await activeBrowser?.close();
  process.exitCode = 1;
});
