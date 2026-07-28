const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: 'production-smoke.test.js',
  timeout: 30000,
  retries: process.env.CI === 'true' ? 0 : 1,
  use: {
    baseURL: process.env.GODFIN_E2E_BASE_URL || 'http://127.0.0.1:5200',
    browserName: 'chromium',
    headless: process.env.CI === 'true',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['json', { outputFile: 'reports/results.json' }],
  ],
  outputDir: 'reports/test-artifacts',
});
