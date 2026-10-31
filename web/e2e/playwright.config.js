// The admin panel in a real browser against a real backend: the API and web/public on one origin
// (uvicorn app.ops.devserver:app), as nginx serves them in production. CI job web-e2e; locally:
//   BASE_URL=http://127.0.0.1:8000 ADMIN_PASSWORD=... npx playwright test
// The tests create their own data through the API, so they run on any database with an admin user.
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 120_000,
  globalTimeout: 20 * 60_000, // the whole run: a hang between tests fails instead of holding the CI job
  expect: { timeout: 15_000 },
  workers: 1, // one shared database: payroll settings and month runs are company-wide
  retries: 0, // a failure is a finding, not a flake
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
    locale: 'ar-KW',
    timezoneId: 'Asia/Kuwait',
    viewport: { width: 1360, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // a browser already on the machine (e.g. CHROMIUM_PATH=/opt/pw-browsers/...), else Playwright's own
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
});
