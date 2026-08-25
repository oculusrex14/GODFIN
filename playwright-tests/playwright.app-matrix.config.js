const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: 'accessibility-smoke.test.js',
  timeout: 45_000,
  retries: 0,
  fullyParallel: false,
  use: {
    baseURL: process.env.GODFIN_E2E_BASE_URL || 'http://127.0.0.1:5200',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  reporter: [['list']],
  outputDir: 'reports/app-matrix-artifacts',
});
