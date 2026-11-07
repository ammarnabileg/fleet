// Accessibility of the shared kit: tabs that a screen reader and a keyboard can use (the chosen one marked from the first
// draw, arrows and Home/End, each tab tied to its panel), text and buttons readable in both themes (WCAG AA), settings
// chosen by name and not typed as codes, numbers typed left to right, and a form that keeps what was typed (a tap beside
// it, a session that ended while it was open).
const { test, expect, settled, clearToasts } = require('./fixtures');

test('tabs: chosen from the first draw, tied to their panels, moved with the arrow keys', async ({ admin }) => {
  await admin.goto('/admin.html#/finance?tab=entries');
  await settled(admin);
  const tab = (k) => admin.locator(`#view [data-tabs=fin] [role=tab][data-tab=${k}]`);
  await expect(tab('entries')).toHaveAttribute('aria-selected', 'true');
  await expect(tab('entries')).toHaveAttribute('tabindex', '0');
  await expect(tab('expenses')).toHaveAttribute('aria-selected', 'false');
  await expect(tab('expenses')).toHaveAttribute('tabindex', '-1');
  // each tab names its panel, and the panel names its tab back
  for (const k of ['expenses', 'entries', 'balance', 'chart', 'periods']) {
    const id = await tab(k).getAttribute('aria-controls');
    const panel = admin.locator('#' + id);
    await expect(panel).toHaveAttribute('role', 'tabpanel');
    await expect(panel).toHaveAttribute('aria-labelledby', await tab(k).getAttribute('id'));
  }
  await expect(admin.locator('#' + (await tab('entries').getAttribute('aria-controls')))).toBeVisible();

  // the page reads right to left: ← is the next tab, → the previous; Home and End the first and the last
  await tab('entries').focus();
  await admin.keyboard.press('ArrowLeft');
  await expect(tab('balance')).toBeFocused();
  await expect(tab('balance')).toHaveAttribute('aria-selected', 'true');
  await expect(tab('entries')).toHaveAttribute('aria-selected', 'false');
  await expect(admin.locator('#' + (await tab('balance').getAttribute('aria-controls')))).toBeVisible();
  await expect(admin).toHaveURL(/tab=balance/);
  await settled(admin);
  await admin.keyboard.press('ArrowRight');
  await expect(tab('entries')).toBeFocused();
  await admin.keyboard.press('End');
  await expect(tab('periods')).toHaveAttribute('aria-selected', 'true');
  await settled(admin);
  await admin.keyboard.press('ArrowLeft'); // past the last: back to the first
  await expect(tab('expenses')).toHaveAttribute('aria-selected', 'true');
  await admin.keyboard.press('Home');
  await expect(tab('expenses')).toBeFocused();
  await settled(admin);
});

test('buttons, text and status pills meet WCAG AA contrast in light and dark', async ({ admin }) => {
  await admin.goto('/admin.html#/custody');
  await settled(admin);
  const measure = () => admin.evaluate(() => {
    const rgb = (s) => (s.match(/[\d.]+/g) || []).map(Number);
    const lum = ([r, g, b]) => [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
      .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    const host = document.createElement('div');
    host.className = 'card';
    host.innerHTML = '<button class="btn btn-primary">a</button><button class="btn btn-success">a</button><button class="btn btn-danger-solid">a</button>'
      + '<button class="btn btn-soft">a</button><span class="pill g">a</span><span class="pill o">a</span><span class="pill r">a</span>'
      + '<span class="pill b">a</span><span class="pill n">a</span><span class="muted">a</span><span class="text-3">a</span>';
    document.getElementById('view').appendChild(host);
    const surface = rgb(getComputedStyle(host).backgroundColor);
    const out = {};
    [...host.children].forEach((el) => {
      const cs = getComputedStyle(el), bg = rgb(cs.backgroundColor);
      const back = bg.length === 4 && bg[3] < 1 ? bg.slice(0, 3).map((v, i) => v * bg[3] + surface[i] * (1 - bg[3])) : bg.length ? bg : surface;
      out[el.className] = Math.round(ratio(rgb(cs.color), bg.length === 4 && bg[3] === 0 ? surface : back) * 100) / 100;
    });
    host.remove();
    return out;
  });
  for (const theme of ['light', 'dark']) {
    await admin.evaluate((t) => window.BT.theme.set(t), theme);
    const r = await measure();
    for (const [cls, v] of Object.entries(r)) expect(v, `${theme}: ${cls}`).toBeGreaterThanOrEqual(4.5);
  }
  await admin.evaluate(() => window.BT.theme.set('light'));
});

test('onboarding settings are chosen by name, not typed as codes', async ({ admin, api }) => {
  const before = (await api.get('/settings')).onboarding;
  const types = await api.get('/document-types');
  const name = (code) => types.find((t) => t.code === code).name.ar;
  await admin.goto('/admin.html#/settings?tab=system');
  await settled(admin);
  const form = admin.locator('form[data-sec=onboarding]');
  const docs = form.locator('[data-choices="onboarding.required_documents"]');
  for (const code of before.value.required_documents) {
    await expect(docs.locator(`input[value="${code}"]`)).toBeChecked();
    await expect(docs).toContainText(name(code));
  }
  await expect(form.locator('[data-choices="onboarding.vehicle_photos"]')).toContainText('الأمام');
  // no code to type anywhere in the section
  await expect(form.locator('input[type=text], input:not([type])')).toHaveCount(0);
  const dropped = before.value.required_documents[before.value.required_documents.length - 1];
  await docs.locator(`input[value="${dropped}"]`).uncheck();
  await form.locator('[type=submit]').click();
  await expect.poll(async () => (await api.get('/settings')).onboarding.value.required_documents)
    .toEqual(before.value.required_documents.filter((c) => c !== dropped));
  const now = (await api.get('/settings')).onboarding;
  await api.put('/settings/onboarding', { version: now.version, value: before.value }); // as it was, for the other tests
});

test('a form keeps what was typed: a tap beside it, and a session that ended while it was open', async ({ admin }) => {
  admin.allow(/HTTP 401 (POST|GET) .*\/api\/v1\/(branches|auth\/me)/);
  await admin.goto('/admin.html#/settings?tab=users');
  await settled(admin);
  await admin.locator('#view [data-add]').click();
  const dlg = admin.locator('.overlay[data-open]').last();
  // phone and user name are typed left to right in the Arabic form
  await expect(dlg.locator('[name=phone]')).toHaveAttribute('dir', 'ltr');
  await expect(dlg.locator('[name=username]')).toHaveAttribute('dir', 'ltr');
  await dlg.locator('[name=full_name]').fill('موظف الاختبار');
  await admin.mouse.click(5, 5); // the backdrop, beside the form
  await expect(dlg).toBeVisible();
  await expect(dlg.locator('[name=full_name]')).toHaveValue('موظف الاختبار');
  await expect(admin.locator('.toast.warning')).toBeVisible();
  await admin.keyboard.press('Escape'); // closing on purpose still works
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  // the session ends while a new branch is being typed: the form stays, then saves once signed in again
  await admin.goto('/admin.html#/settings?tab=branches');
  await settled(admin);
  await admin.locator('#view [data-add]').click();
  const form = admin.locator('.overlay[data-open]').last();
  const n = String(Date.now() % 1e6);
  await form.locator('[name=ar]').fill('فرع الجلسة ' + n);
  await form.locator('[name=en]').fill('Session branch ' + n);
  await admin.context().clearCookies();
  await clearToasts(admin);
  await form.locator('[type=submit]').click();
  await expect(admin.locator('.toast.error')).toContainText('انتهت جلستك');
  await expect(form).toBeVisible();
  await expect(admin).toHaveURL(/admin\.html/);
  await expect(form.locator('[name=ar]')).toHaveValue('فرع الجلسة ' + n);
  // signed in again in another tab
  const other = await admin.context().newPage();
  await other.goto('/login.html');
  await other.fill('#u', process.env.ADMIN_USERNAME || 'admin');
  await other.fill('#p', process.env.ADMIN_PASSWORD || 'correct-horse-battery');
  await other.click('#step1 [type=submit]');
  await other.waitForURL(/admin\.html/);
  await other.close();
  await form.locator('[type=submit]').click();
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);
  await expect(admin.locator('#view')).toContainText('فرع الجلسة ' + n);
});
