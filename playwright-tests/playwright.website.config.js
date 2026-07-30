const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: 'website-product.test.js',
  timeout: 30000,
  retries: process.env.CI === 'true' ? 0 : 1,
  use: {
    baseURL:
      process.env.GODFIN_WEBSITE_BASE_URL || 'http://127.0.0.1:5300',
    browserName: 'chromium',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
  outputDir: 'reports/website-artifacts',
});
