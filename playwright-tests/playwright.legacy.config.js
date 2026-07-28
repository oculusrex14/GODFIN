const { defineConfig } = require('@playwright/test');
const production = require('./playwright.config');

module.exports = defineConfig({
  ...production,
  testMatch: '**/*.test.js',
  testIgnore: 'production-smoke.test.js',
  reporter: [['list']],
});
