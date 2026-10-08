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

  /** A file uploaded from the office (a photo or a PDF): its sha256. */
  async upload(name, mimeType, buffer) {
    const res = await this.ctx.fetch('/api/v1/files', {
      method: 'POST', headers: { 'X-CSRF-Token': this.csrf }, multipart: { file: { name, mimeType, buffer } },
    });
    const text = await res.text();
    if (!res.ok()) throw new Error(`POST /files -> ${res.status()} ${text}`);
    return JSON.parse(text).sha256;
  }

  /** A driver's phone, signed in through an activation link as the app does: returns a client for /driver/*.
   *  With onboarding, the link opens his self-registration. */
  async driverPhone(employeeId, deviceUid, { onboarding = false } = {}) {
    await this.put(`/employees/${employeeId}/app-access`, { app_access: 'active' });
    const link = await this.post(`/employees/${employeeId}/activation-link`, { channel: 'manual', onboarding });
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
/** A small valid PDF, made unique by a comment. */
function pdf() {
  return Buffer.from('%PDF-1.4\n%' + require('crypto').randomBytes(8).toString('hex') + '\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
    + '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n'
    + 'trailer<</Root 1 0 R>>\n%%EOF\n');
}

// unique per run and per call: codes, employee numbers, phones (Kuwaiti mobile: 5, 6 or 9 then 7 digits)
let seq = 0;
const runId = String(Date.now() % 100000).padStart(5, '0');
function uid() { seq += 1; return runId + String(seq).padStart(2, '0'); }
function phone() { return '+9655' + uid(); }

/** The view has finished loading: no spinner left in it. */
// Types in the page's table search, then waits until the rows found are drawn: the search applies after a pause, and
// a row taken before that (its menu opened, its box ticked) is the old list's, about to be replaced.
async function search(page, q, within = '#view') {
  await page.fill(within + ' input[type=search]', q);
  await expect(page.locator(within + ' [aria-busy]')).toHaveCount(0);
}

async function settled(page) {
  await expect(page.locator('#view .spinner')).toHaveCount(0);
}

/** Removes the toasts on screen, before an action whose toast the test checks: a toast still showing from an earlier
 * action (they stay up to 8 s) would otherwise answer for it, and the test would go on before the action finished. */
async function clearToasts(page) {
  await page.evaluate(() => document.querySelectorAll('.toast').forEach((t) => t.remove()));
}

/** Fails the test on any page error, console error or failed request the test did not allow (page.allow(regex)), and
 * prints what the browser did when the test fails (CI keeps no screenshots this session can open). */
function track(page, who) {
  // SLOW_FRAMES=250: every animation frame comes 250 ms late, as on a busy CI machine or a slow phone, so a test that
  // depends on the frame timing fails here every time instead of once in a while in CI
  const slow = Number(process.env.SLOW_FRAMES || 0);
  if (slow) {
    page.addInitScript((ms) => {
      window.requestAnimationFrame = (fn) => setTimeout(() => fn(performance.now()), ms);
      window.cancelAnimationFrame = (id) => clearTimeout(id); // a removed map cancels its next frame
    }, slow);
  }
  // SLOW_SAVES=800: every save (any API call but a GET) answers 800 ms late, as on a busy server, so a test that goes on
  // before the save it made has finished fails here every time instead of once in a while in CI
  const saves = Number(process.env.SLOW_SAVES || 0);
  const ready = saves ? page.route('**/api/v1/**', async (r) => {
    if (r.request().method() !== 'GET') await new Promise((ok) => setTimeout(ok, saves));
    await r.continue();
  }) : Promise.resolve();
  const errors = [];
  const allowed = [];
  const trail = [];
  const t0 = Date.now();
  const note = (line) => trail.push(String(Date.now() - t0).padStart(6) + 'ms ' + line);
  const path = (url) => url.replace(/^https?:\/\/[^/]+/, '');
  page.on('pageerror', (e) => {
    errors.push(who + ' page error: ' + e.message);
    note('PAGE ERROR ' + (e.stack || e.message).split('\n').slice(0, 6).join('\n           '));
  });
  page.on('console', (m) => {
    note('console.' + m.type() + ' ' + m.text());
    // failed loads are reported by the response listener below, with their URL
    if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(who + ' console: ' + m.text());
    if (/missing icon/.test(m.text())) errors.push(who + ' console: ' + m.text()); // an icon drawn empty
  });
  page.on('request', (r) => { if (r.url().includes('/api/')) note('→ ' + r.method() + ' ' + path(r.url())); });
  page.on('requestfailed', (r) => note('✗ ' + r.method() + ' ' + path(r.url()) + ' ' + (r.failure() || {}).errorText));
  page.on('framenavigated', (f) => { if (f === page.mainFrame()) note('at ' + path(f.url())); });
  page.on('response', (r) => {
    const url = r.url();
    if (url.includes('/api/')) note('← ' + r.status() + ' ' + r.request().method() + ' ' + path(url));
    if (r.status() >= 400 && !url.endsWith('/api/v1/auth/me')) errors.push(`${who} HTTP ${r.status()} ${r.request().method()} ${url}`);
  });
  page.allow = (pattern) => allowed.push(pattern);
  return {
    ready,
    async finish(testInfo) {
      const unexpected = errors.filter((e) => !allowed.some((p) => p.test(e)));
      if (testInfo.status !== testInfo.expectedStatus || unexpected.length) {
        const dialogs = await page.evaluate(() => [...document.querySelectorAll('.overlay')].map((o) => o.className + ' | '
          + [...o.querySelectorAll('.field.invalid')].map((f) => f.innerText.replace(/\s+/g, ' ')).join(' / '))).catch(() => []);
        console.log(`--- ${who} browser trail of "${testInfo.title}" ---\n${trail.slice(-250).join('\n')}\n--- dialogs: ${JSON.stringify(dialogs)}`);
      }
      expect(unexpected, 'page, console or API errors').toEqual([]);
    },
  };
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
    const t = track(page, 'admin');
    await t.ready;
    await page.goto('/login.html');
    await page.fill('#u', ADMIN.username);
    await page.fill('#p', ADMIN.password);
    await page.click('#step1 [type=submit]');
    await page.waitForURL(/admin\.html/);
    await settled(page);
    await use(page);
    await t.finish(testInfo);
  },

  /** A second browser, signed out, for the other side of a flow (a maintenance center's portal), watched the same way. */
  portal: async ({ browser, baseURL, locale, timezoneId }, use, testInfo) => {
    const ctx = await browser.newContext({ baseURL, locale, timezoneId, viewport: { width: 1360, height: 900 } });
    const page = await ctx.newPage();
    const t = track(page, 'portal');
    await t.ready;
    await use(page);
    await t.finish(testInfo);
    await ctx.close();
  },
});

const CENTER_PASSWORD = 'temporary-pass-1', CENTER_NEW_PASSWORD = 'center-garage-2026-strong';

/** A maintenance center with one portal user on a temporary password. */
async function centerWithUser(api, n) {
  const center = await api.post('/maintenance/centers', { name: 'مركز النور ' + n, specialty: 'ميكانيكا وسمكرة' });
  const username = 'noor' + n;
  await api.post(`/maintenance/centers/${center.id}/users`, { username, full_name: 'مسؤول النور', password: CENTER_PASSWORD });
  return { center, username };
}

/** The center's first sign-in: the temporary password must be changed before anything else. */
async function centerSignIn(portal, username) {
  await portal.goto('/login.html');
  await portal.fill('#u', username);
  await portal.fill('#p', CENTER_PASSWORD);
  await portal.click('#step1 [type=submit]');
  await portal.waitForURL(/center\.html/);
  const pw = portal.locator('.overlay[data-open]').last();
  await pw.locator('[name=old]').fill(CENTER_PASSWORD);
  await pw.locator('[name=pw]').fill(CENTER_NEW_PASSWORD);
  await pw.locator('[name=pw2]').fill(CENTER_NEW_PASSWORD);
  await pw.locator('button[type=submit]').click();
  await expect(pw).toBeHidden();
}

/** A time as a datetime field shows it in Kuwait (UTC+3 all year, no daylight saving): "2026-10-05T13:00". */
function kuwaitInput(ms) { return new Date(ms + 3 * 3600e3).toISOString().slice(0, 16); }

module.exports = { test, expect, uid, phone, settled, search, clearToasts, jpeg, pdf, centerWithUser, centerSignIn, kuwaitInput };
