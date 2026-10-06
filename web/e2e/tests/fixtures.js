// Shared fixtures: `api` (the admin API, signed in, for setting up data) and `admin` (a signed-in browser page that
// fails the test on any page error, console error or failed API call it was not told to expect).
const base = require('@playwright/test');

const { expect } = base;
const ADMIN = { username: process.env.ADMIN_USERNAME || 'admin', password: process.env.ADMIN_PASSWORD || 'correct-horse-battery' };

class Api {
  constructor(ctx) {
    this.ctx = ctx;
    this.csrf = null;
  }

  async call(method, path, body, headers) {
    const res = await this.ctx.fetch('/api/v1' + path, {
      method,
      data: body,
      headers: Object.assign({ 'Accept-Language': 'en' }, this.csrf ? { 'X-CSRF-Token': this.csrf } : {}, headers || {}),
    });
    const text = await res.text();
    if (!res.ok()) throw new Error(`${method} ${path} -> ${res.status()} ${text}`);
    return text ? JSON.parse(text) : null;
  }

  get(path) { return this.call('GET', path); }
  post(path, body) { return this.call('POST', path, body || {}); }
  put(path, body) { return this.call('PUT', path, body); }
  patch(path, body) { return this.call('PATCH', path, body); }

  /** A driver's phone, signed in through an activation link as the app does: returns a client for /driver/*. */
  async driverPhone(employeeId, deviceUid) {
    await this.put(`/employees/${employeeId}/app-access`, { app_access: 'active' });
    const link = await this.post(`/employees/${employeeId}/activation-link`, { channel: 'manual', onboarding: false });
    const token = link.url.split('#t=')[1];
    const t = await this.call('POST', '/driver/auth/activate', { token, device_uid: deviceUid, model: 'E2E' });
    const auth = { Authorization: 'Bearer ' + t.access_token };
    const self = this;
    const answer = (method, path) => async (r) => {
      const text = await r.text();
      if (!r.ok()) throw new Error(`${method} ${path} -> ${r.status()} ${text}`);
      return text ? JSON.parse(text) : null;
    };
    return {
      call: (method, path, body) => self.ctx.fetch('/api/v1' + path, { method, data: body, headers: auth }).then(answer(method, path)),
      /** A photo from the gallery, or the camera (a JPEG never sent before, as the server refuses a reused one). */
      photo: (source) => {
        return self.ctx.fetch('/api/v1/driver/files?source=' + (source || 'upload'), {
          method: 'POST', headers: auth, multipart: { file: { name: 'shot.jpg', mimeType: 'image/jpeg', buffer: jpeg() } },
        }).then(answer('POST', '/driver/files')).then((f) => f.sha256);
      },
    };
  }
}

/** A JPEG never seen before: the server refuses a photo it already has. */
function jpeg() { return Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), require('crypto').randomBytes(64)]); }

// unique per run and per call: codes, employee numbers, phones (Kuwaiti mobile: 5, 6 or 9 then 7 digits)
let seq = 0;
const runId = String(Date.now() % 100000).padStart(5, '0');
function uid() { seq += 1; return runId + String(seq).padStart(2, '0'); }
function phone() { return '+9655' + uid(); }

/** The view has finished loading: no spinner left in it. */
async function settled(page) {
  await expect(page.locator('#view .spinner')).toHaveCount(0);
}

const test = base.test.extend({
  api: async ({ playwright, baseURL }, use) => {
    const ctx = await playwright.request.newContext({ baseURL });
    const api = new Api(ctx);
    const login = await api.call('POST', '/auth/login', ADMIN);
    api.csrf = login.csrf_token;
    await use(api);
    await ctx.dispose();
  },

  admin: async ({ page }, use, testInfo) => {
    const errors = [];
    const allowed = [];
    const trail = []; // what the browser did, printed when the test fails (CI keeps no screenshots we can open)
    const t0 = Date.now();
    const note = (line) => trail.push(String(Date.now() - t0).padStart(6) + 'ms ' + line);
    page.on('pageerror', (e) => { errors.push('page error: ' + e.message); note('PAGE ERROR ' + e.message); });
    page.on('console', (m) => {
      note('console.' + m.type() + ' ' + m.text());
      // failed loads are reported by the response listener below, with their URL
      if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text());
    });
    page.on('request', (r) => { if (r.url().includes('/api/')) note('→ ' + r.method() + ' ' + r.url().replace(/^https?:\/\/[^/]+/, '')); });
    page.on('requestfailed', (r) => note('✗ ' + r.method() + ' ' + r.url() + ' ' + (r.failure() || {}).errorText));
    page.on('framenavigated', (f) => { if (f === page.mainFrame()) note('at ' + f.url().replace(/^https?:\/\/[^/]+/, '')); });
    page.on('response', (r) => {
      const url = r.url();
      if (url.includes('/api/')) note('← ' + r.status() + ' ' + r.request().method() + ' ' + url.replace(/^https?:\/\/[^/]+/, ''));
      if (r.status() >= 400 && !url.endsWith('/api/v1/auth/me')) errors.push(`HTTP ${r.status()} ${r.request().method()} ${url}`);
    });
    page.allow = (pattern) => allowed.push(pattern);
    await page.goto('/login.html');
    await page.fill('#u', ADMIN.username);
    await page.fill('#p', ADMIN.password);
    await page.click('#step1 [type=submit]');
    await page.waitForURL(/admin\.html/);
    await settled(page);
    await use(page);
    if (testInfo.status !== testInfo.expectedStatus) {
      const dialogs = await page.evaluate(() => [...document.querySelectorAll('.overlay')].map((o) => o.className + ' | '
        + [...o.querySelectorAll('.field.invalid')].map((f) => f.innerText.replace(/\s+/g, ' ')).join(' / '))).catch(() => []);
      console.log(`--- browser trail of "${testInfo.title}" ---\n${trail.slice(-150).join('\n')}\n--- dialogs: ${JSON.stringify(dialogs)}`);
    }
    const unexpected = errors.filter((e) => !allowed.some((p) => p.test(e)));
    expect(unexpected, 'page, console or API errors').toEqual([]);
  },
});

module.exports = { test, expect, uid, phone, settled, jpeg };
