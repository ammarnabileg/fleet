// A delivery platform made from the panel without an Excel sample (what its drivers send each day chosen in the form),
// then given to a driver in his form, and to several drivers at once from the list.
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');

test('a platform without Excel, given to a driver in his form', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المنصة ' + n, en: 'Platform company ' + n } });
  const e = await api.post('/employees', {
    employee_number: 'PL' + n, name: { ar: 'سائق المنصة ' + n, en: 'Platform driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/payroll?tab=platforms');
  await settled(admin);
  await expect(admin.locator('#plat-template')).toBeVisible(); // the Excel sample stays an option
  await admin.click('#plat-new');
  const m = top();
  await expect(m.locator('[data-daily]')).toContainText('اليوم صالح');
  await expect(m.locator('[data-daily]')).toContainText('عدد الطلبات');
  await expect(m.locator('[data-daily]')).toContainText('الكاش');
  await m.locator('[name=code]').fill('pl' + n);
  await m.locator('[name=name_ar]').fill('منصة ' + n);
  await m.locator('[name=name_en]').fill('Platform ' + n);
  await m.locator('[name=dy_orders]').uncheck();
  await m.locator('[name=dy_cash]').uncheck();
  await m.locator('[name=dy_valid_day]').check(); // whether the platform counted his day valid, only
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('أُضيفت المنصة');
  const made = (await api.get('/payroll/platforms')).find((p) => p.code === 'pl' + n);
  expect([made.daily_fields, made.driver_fields, made.columns, made.is_active]).toEqual([['valid_day'], [], [], true]);
  await expect(admin.locator('#view .card', { hasText: 'منصة ' + n })).toContainText('اليوم صالح');

  await admin.goto('/admin.html#/employees');
  await admin.reload(); // the companies are read once when the panel opens
  await settled(admin);
  await search(admin, e.employee_number);
  await admin.locator('#view tbody tr', { hasText: e.employee_number }).click();
  await top().locator('[data-x=edit]').click();
  await top().locator('[name=platform_id]').selectOption(String(made.id));
  await top().locator('[name=platform_driver_id]').fill('D-' + n);
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('تم حفظ التعديلات');
  const saved = await api.get('/employees/' + e.id);
  expect([saved.platform_id, saved.platform_driver_id]).toEqual([made.id, 'D-' + n]);
});

test('several drivers put on a platform from the list', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة التعيين ' + n, en: 'Assign company ' + n } });
  const platform = await api.post('/payroll/platforms', { code: 'as' + n, name: { ar: 'منصة التعيين ' + n, en: 'Assign ' + n } });
  const driver = (i) => api.post('/employees', {
    employee_number: 'AS' + n + i, name: { ar: 'سائق التعيين ' + n + ' ' + i, en: 'Assign driver ' + n + ' ' + i }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const drivers = [await driver(1), await driver(2)];
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/employees');
  await admin.reload();
  await settled(admin);
  await search(admin, 'AS' + n);
  const rows = admin.locator('#view tbody tr', { hasText: 'AS' + n });
  await expect(rows).toHaveCount(2);
  await rows.nth(0).locator('input[type=checkbox]').check();
  await rows.nth(1).locator('input[type=checkbox]').check();
  await admin.getByRole('button', { name: 'تعيين منصة' }).click();
  await top().locator('[name=platform_id]').selectOption(String(platform.id));
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('عُيّنت المنصة لـ 2 سائق');
  for (const d of drivers) expect((await api.get('/employees/' + d.id)).platform_id).toBe(platform.id);
});
