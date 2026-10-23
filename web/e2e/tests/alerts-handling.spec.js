// Handling an alert apart from seeing it: «تم الاطلاع» keeps it open, it is escalated (assigned) to another user with a
// reason, then closed with what was done; each step shows in its log and the audit log. The list is searched and
// filtered, the most severe first.
const { test, expect, uid, settled, clearToasts } = require('./fixtures');

async function fineWithNobodyDriving(api, n) {
  const company = await api.post('/companies', { name: { ar: 'شركة المعالجة ' + n, en: 'Handling company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '6/' + n.slice(-6), company_id: company.id, last_odometer_km: 100 });
  await api.post('/fines', { vehicle_id: vehicle.id, occurred_at: new Date(Date.now() - 3600e3).toISOString(), violation: 'وقوف ' + n, amount: '5' });
  return vehicle;
}

test('an alert seen, escalated to another user, handled, with its log', async ({ admin, api }) => {
  const n = uid();
  const vehicle = await fineWithNobodyDriving(api, n);
  const role = 'fines_' + n;
  await api.post('/roles', { code: role, name: { ar: 'مخالفات ' + n, en: 'Fines ' + n }, permissions: ['fines.manage', 'fines.view'] });
  const boss = await api.post('/users', { username: 'boss' + n, full_name: 'المدير ' + n, password: 'a-long-password-' + n, role_codes: [role], all_companies: true, company_ids: [] });

  await admin.goto('/admin.html#/alerts');
  await settled(admin);
  const table = admin.locator('#alerts-table');
  await table.locator('input[type=search]').fill(vehicle.plate_number); // a plate, searched on the server
  await expect(table.locator('[aria-busy]')).toHaveCount(0);
  const row = table.locator('tbody tr', { hasText: vehicle.plate_number });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText('جديد');
  await row.locator('[data-ack]').click();
  await expect(row).toContainText('اطُّلع عليه'); // seen: still in the open list
  await expect(row.locator('[data-ack]')).toHaveCount(0);

  await row.locator('[data-row-open]').click(); // «التفاصيل»
  const drawer = admin.locator('.overlay[data-open]').last();
  await expect(drawer).toContainText('سجل الإجراءات');
  await expect(drawer.locator('[data-alert-log]')).toContainText('تم الاطلاع');
  await drawer.locator('[data-x=escalate]').click();
  const form = admin.locator('.overlay[data-open]').last();
  await form.locator('[name=user]').selectOption(boss.public_id);
  await form.locator('[name=note]').fill('يحتاج قرار المدير');
  await clearToasts(admin);
  await form.getByRole('button', { name: 'تصعيد', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('صُعّد التنبيه');
  await expect(drawer.locator('[data-alert-log]')).toContainText('صُعّد إلى المدير ' + n);
  await expect(drawer.locator('[data-alert-log]')).toContainText('يحتاج قرار المدير');
  await expect(row).toContainText('مُصعّد');

  await drawer.locator('[data-x=resolve]').click();
  const confirm = admin.locator('.overlay[data-open]').last();
  await confirm.locator('[name=reason]').fill('حُددت المخالفة على الشركة');
  await clearToasts(admin);
  await confirm.getByRole('button', { name: 'إغلاق التنبيه' }).click();
  await expect(admin.locator('.toast').last()).toContainText('أُغلق التنبيه');
  await expect(drawer.locator('[data-alert-log]')).toContainText('عولج وأُغلق');
  await expect(drawer.locator('[data-x=resolve]')).toHaveCount(0);
  await admin.keyboard.press('Escape');
  await expect(table.locator('tbody tr', { hasText: vehicle.plate_number })).toHaveCount(0); // no longer open
  await table.locator('[data-chip=resolved]').click();
  await expect(table.locator('tbody tr', { hasText: vehicle.plate_number })).toContainText('حُددت المخالفة على الشركة');
  const audit = await api.get('/audit?entity_type=alert&limit=50');
  expect(audit.map((e) => e.action)).toEqual(expect.arrayContaining(['alert.acknowledged', 'alert.escalated', 'alert.resolved']));
});

test('the most severe first, filtered by severity and kind', async ({ admin, api }) => {
  const n = uid();
  await fineWithNobodyDriving(api, n);
  await admin.goto('/admin.html#/alerts');
  await settled(admin);
  const table = admin.locator('#alerts-table');
  const sev = await api.get('/alerts?sort=severity&limit=50');
  const rank = { critical: 0, warning: 1, info: 2 };
  expect(sev.map((a) => rank[a.severity])).toEqual([...sev.map((a) => rank[a.severity])].sort());
  await table.locator('[data-f=kind]').selectOption('fine_no_driver');
  await expect(table.locator('[aria-busy]')).toHaveCount(0);
  const rows = table.locator('tbody tr');
  await expect(rows.first()).toContainText('مخالفة بلا سائق');
  for (const text of await rows.allInnerTexts()) expect(text).toContain('مخالفة بلا سائق');
  await table.locator('[data-f=severity]').selectOption('critical');
  await expect(table.locator('tbody tr', { hasText: 'مخالفة بلا سائق' })).toHaveCount(0); // a fine is a warning
});
