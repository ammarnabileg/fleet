// The employee form picks the nationality from the list the driver's app shows (one spelling for every report),
// searched in Arabic or English; a typed value is refused.
const { test, expect, uid, settled, search, clearToasts } = require('./fixtures');

test('the nationality is picked from the list, in Arabic or English', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الجنسية ' + n, en: 'Nationality company ' + n } });
  const e = await api.post('/employees', {
    employee_number: 'NT' + n, name: { ar: 'موظف الجنسية ' + n, en: 'Nationality ' + n }, company_id: company.id, nationality: 'مصر',
  });
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/employees');
  await admin.reload(); // the companies are read once when the panel opens
  await settled(admin);
  await search(admin, e.employee_number);
  await admin.locator('#view tbody tr', { hasText: e.employee_number }).click();
  await top().locator('[data-x=edit]').click();
  const field = top().locator('[name=nationality]');
  await expect(field).toHaveValue('مصر — Egypt');
  const options = await field.evaluate((el) => [...el.list.options].map((o) => o.value));
  expect(options).toContain('الهند — India');
  expect(options.length).toBeGreaterThan(190);

  await field.fill('هندي'); // typed, not picked
  await top().locator('button[type=submit]').click();
  await expect(top().locator('.field.invalid')).toContainText('اختر من القائمة');
  await field.fill('الهند — India');
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('تم حفظ التعديلات');
  expect((await api.get('/employees/' + e.id)).nationality).toBe('الهند');
});
