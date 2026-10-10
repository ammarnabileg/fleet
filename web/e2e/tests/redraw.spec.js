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

// A save whose answer comes back after the user went to another page leaves that page alone: it redrew whatever page
// was showing, so the filter the user had just chosen there went back to its default.
test('a save answered after the user moved on does not redraw the page he is on', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الرد المتأخر ' + n, en: 'Late answer ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '46/' + n.slice(-6), company_id: company.id, last_odometer_km: 1000 });
  const accident = await api.post('/accidents', { vehicle_id: vehicle.id, description: 'خدش في الباب' });
  await admin.goto('/admin.html#/accidents/' + accident.id);
  await settled(admin);
  // the server takes a while to answer the cancellation
  await admin.route('**/accidents/*/cancel', async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
  await admin.click('[data-action="acc-cancel"]');
  const confirm = admin.locator('.overlay[data-open]').last();
  await confirm.locator('[name=reason]').fill('بلاغ مكرر');
  const answered = admin.waitForResponse((r) => r.url().includes('/cancel'));
  await confirm.getByRole('button', { name: 'إلغاء الحادث', exact: true }).click();

  await admin.goto('/admin.html#/deductions'); // before the answer
  await settled(admin);
  await admin.locator('#view .chip', { hasText: 'كل المعتمدة' }).click();
  await settled(admin);
  const asked = [];
  admin.on('request', (r) => { if (r.url().includes('/api/v1/deductions')) asked.push(r.url()); });
  await answered;
  await expect.poll(() => admin.evaluate(() => document.querySelectorAll('.toast').length)).toBeGreaterThan(0); // its toast: the answer was handled
  await expect(admin.locator('#view .chip.active')).toContainText('كل المعتمدة');
  expect(asked).toEqual([]); // the deductions page was not reloaded
  expect((await api.get('/accidents/' + accident.id)).status).toBe('cancelled');
});
