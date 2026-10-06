// A panel that redraws itself after a save keeps one click handler: the next click opens one form and sends one
// request (a handler added on every redraw opened two stacked forms, and a toggle sent two requests from stale rows).
const { test, expect, uid, settled, clearToasts } = require('./fixtures');

test('after a save, the next click opens one form', async ({ admin, api }) => {
  const n = uid();
  const platform = await api.post('/payroll/platforms', { code: 'r' + n, name: { ar: 'منصة ' + n, en: 'Platform ' + n } });
  await admin.goto('/admin.html#/payroll?tab=schemes');
  await settled(admin);
  const open = admin.locator('.overlay[data-open]');
  for (const code of ['first', 'second', 'third']) {
    await admin.click(`[data-new="${platform.id}"]`);
    await expect(open).toHaveCount(1);
    const m = open.last();
    await m.locator('[name=code]').fill(code);
    await m.locator('[name=name_ar]').fill('نظام ' + code);
    await m.locator('[name=name_en]').fill(code);
    await m.locator('[name=per_order]').fill('0.300');
    await m.locator('button[type=submit]').click();
    await expect(open).toHaveCount(0);
  }
  const mine = (await api.get('/payroll/schemes')).filter((s) => s.platform_id === platform.id);
  expect(mine.map((s) => s.code).sort()).toEqual(['first', 'second', 'third']);
});

test('a status toggled twice sends one request each time and ends where it started', async ({ admin, api }) => {
  const code = 'leave' + uid();
  await api.post('/employment-statuses', { code, name: { ar: 'إجازة ' + code, en: 'Leave ' + code }, is_working: false, is_terminal: false });
  const patches = [];
  admin.on('request', (r) => { if (r.method() === 'PATCH' && r.url().endsWith('/employment-statuses/' + code)) patches.push(r.postDataJSON()); });
  await admin.goto('/admin.html#/settings?tab=statuses');
  await settled(admin);
  await admin.locator('[role=tab][data-tab=statuses]').click();
  await settled(admin);
  const active = async () => (await api.get('/employment-statuses')).find((s) => s.code === code).is_active;
  expect(await active()).toBe(true);
  for (const expected of [false, true]) {
    await clearToasts(admin); // the first toggle's toast says the same
    await admin.locator(`[data-toggle="${code}"]`).click();
    await expect.poll(active).toBe(expected);
    await expect(admin.locator('.toast').last()).toContainText('تم التحديث');
    await settled(admin);
  }
  expect(patches).toEqual([{ is_active: false }, { is_active: true }]);
});
