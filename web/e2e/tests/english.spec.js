// The panel in English: every page and every tab shows no Arabic of its own (the dictionary i18n-en.js covers it),
// reads left to right, and switching back gives the Arabic panel.
const { test, expect, settled } = require('./fixtures');
const fs = require('fs');

const PAGES = [
  'dashboard', 'tracking', 'driver-status', 'alerts', 'vehicles', 'custody', 'odometer', 'daily', 'maintenance', 'accidents', 'fines',
  'cash', 'finance', 'deductions', 'payroll', 'employees', 'attendance', 'reports', 'report-center', 'approvals', 'import', 'settings',
  'app-download', 'broadcasts', 'site', 'integrations', 'audit', 'guide', 'platforms',
];


function leftovers(page) {
  return page.evaluate(() => {
    const AR = /[؀-ۿ]/, out = new Set();
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const p = n.parentElement;
      if (!p || p.closest('script,style,textarea,[data-no-tr]') || !p.getClientRects().length) continue;
      if (AR.test(n.nodeValue)) out.add(n.nodeValue.replace(/\s+/g, ' ').trim());
    }
    document.querySelectorAll('[placeholder],[title],[aria-label],[data-tip]').forEach((e) => {
      ['placeholder', 'title', 'aria-label', 'data-tip'].forEach((a) => { const v = e.getAttribute(a); if (v && AR.test(v)) out.add(v); });
    });
    Object.keys(window.BT.i18nMissing || {}).forEach((t) => out.add(t));
    return [...out];
  });
}

test('every page and tab of the panel reads in English', async ({ admin }) => {
  admin.allow(/\/maps\//);
  // what the server sent (names, notes, places) is data, written in whatever language it was typed in: not the panel's
  let data = '';
  await admin.route('**/api/**', (r) => r.continue()); // no browser cache: every answer comes with its body
  const reading = [];
  admin.on('response', (r) => {
    if (!r.url().includes('/api/') || !(r.headers()['content-type'] || '').includes('json')) return;
    reading.push(r.text().then((t) => { data += JSON.stringify(JSON.parse(t)); }, () => {}).catch(() => {}));
  });
  // a word the server sent, or initials made from one (the avatars)
  const isData = (t) => (t.match(/[\u0600-\u06FF]+/g) || []).every((w) => w.length <= 2 || data.includes(w));
  await admin.goto('/admin.html#/dashboard');
  await admin.evaluate(() => localStorage.setItem('ui.lang', 'en'));
  await admin.reload();
  expect(await admin.evaluate(() => document.documentElement.dir)).toBe('ltr');
  const found = {};
  for (const key of PAGES) {
    await admin.goto('/admin.html#/' + key);
    await admin.waitForFunction((k) => window.BT.A.router && window.BT.A.router.current === k, key);
    await settled(admin);
    await admin.waitForLoadState('networkidle');
    const add = async (where) => {
      // an object put where text goes (a list of cards in a text field) reads «[object Object]» in any language
      if ((await admin.locator('#view').innerText()).includes('[object Object]')) (found['[object Object]'] = found['[object Object]'] || new Set()).add(where);
      await Promise.all(reading); for (const t of (await leftovers(admin)).filter((x) => !isData(x))) (found[t] = found[t] || new Set()).add(where); };
    await add(key);
    const tabs = admin.locator('#view [role=tab]');
    for (let i = 0; i < (await tabs.count()); i++) {
      if (!(await tabs.nth(i).isVisible())) continue;
      await tabs.nth(i).click();
      await settled(admin);
      await add(key + '#' + i);
    }
  }
  const report = Object.fromEntries(Object.entries(found).map(([t, w]) => [t, [...w]]));
  if (process.env.EN_REPORT) fs.writeFileSync(process.env.EN_REPORT, JSON.stringify(report, null, 1));
  expect(Object.keys(report)).toEqual([]);

  // the button in the top bar switches back, and the account keeps the choice for the server's own texts
  await Promise.all([admin.waitForEvent('load'), admin.locator('[data-action=lang]').click()]);
  await expect(admin.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(admin.locator('#tb-title h1')).toHaveText(/[\u0600-\u06FF]/);
  expect((await (await admin.request.get('/api/v1/auth/me')).json()).locale).toBe('ar');
});
