// The maintenance centers' portal reads in English too: its language button switches, and every page, a request and
// an accident, with their forms, show no Arabic left but the data typed by people (names, notes).
const { test, expect, uid, phone, settled, jpeg, pdf, centerWithUser, centerSignIn } = require('./fixtures');

function leftovers(page) {
  return page.evaluate(() => {
    const AR = /[؀-ۿ]/, out = new Set();
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const p = n.parentElement;
      if (!p || p.closest('script,style,textarea,[data-no-tr]') || !p.getClientRects().length) continue;
      if (AR.test(n.nodeValue)) out.add(n.nodeValue.replace(/\s+/g, ' ').trim());
    }
    document.querySelectorAll('[placeholder],[title],[aria-label]').forEach((e) => {
      ['placeholder', 'title', 'aria-label'].forEach((a) => { const v = e.getAttribute(a); if (v && AR.test(v)) out.add(v); });
    });
    Object.keys(window.BT.i18nMissing || {}).forEach((t) => out.add(t));
    return [...out];
  });
}

test('the maintenance centers portal reads in English', async ({ api, portal }) => {
  test.setTimeout(180_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة البوابة ' + n, en: 'Portal company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '9/' + n.slice(-6), make: 'Kia', model: 'Pegas', company_id: company.id, last_odometer_km: 1000 });
  const { center, username } = await centerWithUser(api, n);
  await api.post('/maintenance/requests', { vehicle_id: vehicle.id, center_id: center.id, kind: 'electrical', description: 'battery ' + n, odometer_km: 1000, photos: [] });
  const jpg = () => api.upload('p.jpg', 'image/jpeg', jpeg());
  const acc = await api.post('/accidents', { vehicle_id: vehicle.id, description: 'side hit ' + n, photos: [await jpg(), await jpg(), await jpg()], police_report: await api.upload('p.pdf', 'application/pdf', pdf()) });
  await api.post('/accidents/' + acc.id + '/refer', { center_id: center.id });

  let data = '';
  portal.on('response', (r) => { if (r.url().includes('/api/') && (r.headers()['content-type'] || '').includes('json')) r.text().then((t) => { data += t; }, () => {}); });
  const isData = (t) => (t.match(/[؀-ۿ]+/g) || []).every((w) => w.length <= 2 || data.includes(w));

  await centerSignIn(portal, username);
  await Promise.all([portal.waitForEvent('load'), portal.locator('[data-action=lang]').click()]); // the button in the top bar
  await expect(portal.locator('html')).toHaveAttribute('dir', 'ltr');
  const found = {};
  const add = async (where) => { await portal.waitForTimeout(300); for (const t of (await leftovers(portal)).filter((x) => !isData(x))) (found[t] = found[t] || new Set()).add(where); };
  for (const key of ['requests', 'accidents', 'history', 'invoices']) {
    await portal.goto('/center.html#/' + key);
    await settled(portal);
    await add(key);
  }
  await portal.goto('/center.html#/requests');
  await settled(portal);
  await portal.locator('#view tbody tr').first().click();
  await settled(portal);
  await add('request');
  const acts = portal.locator('#view .btn');
  for (let i = 0; i < Math.min(await acts.count(), 4); i++) { // its forms (quote, invoice...): open, read, close
    if (!(await acts.nth(i).isVisible())) continue;
    await acts.nth(i).click();
    await portal.waitForTimeout(400);
    await add('request form ' + i);
    await portal.keyboard.press('Escape');
  }
  await portal.goto('/center.html#/a/' + acc.id);
  await settled(portal);
  await add('accident');
  await portal.click('[data-est]');
  await portal.waitForTimeout(400);
  await add('estimate form');
  await portal.keyboard.press('Escape');
  await portal.locator('[data-action=user-menu]').last().click();
  await add('user menu');
  const report = Object.fromEntries(Object.entries(found).map(([t, w]) => [t, [...w]]));
  if (process.env.EN_REPORT) require('fs').writeFileSync(process.env.EN_REPORT, JSON.stringify(report, null, 1));
  expect(Object.keys(report)).toEqual([]);
});
