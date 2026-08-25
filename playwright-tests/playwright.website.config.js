const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: 'website-product.test.js',
  timeout: 30000,
  retries: process.env.CI === 'true' ? 0 : 1,
  use: {
    baseURL:
      process.env.GODFIN_WEBSITE_BASE_URL || 'http://127.0.0.1:5300',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
  reporter: [['list']],
  outputDir: 'reports/website-artifacts',
});
