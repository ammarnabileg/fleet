// A table shows 200 rows, or all of them: the server gives at most 200 a request, so they are read in parts.
const { test, expect, settled, uid, phone } = require('./fixtures');

test('a server list shows 200 rows a page, or all of them', async ({ admin, api }) => {
  test.setTimeout(180_000);
  const company = await api.post('/companies', { name: { ar: 'شركة الجدول ' + uid(), en: 'Table company' } });
  let total = (await api.get('/employees?limit=200&offset=200')).length + 200;
  for (let i = 0; total < 230; i++, total++) { // more than 200 employees, whatever the database held
    await api.post('/employees', { employee_number: 'TB' + uid(), name: { ar: 'موظف جدول ' + i, en: 'Table ' + i }, company_id: company.id, is_driver: true, phone: phone() });
  }
  await admin.goto('/admin.html#/employees');
  await settled(admin);
  const rows = admin.locator('#view table tbody tr');
  await admin.locator('#view [data-size]').selectOption('200');
  await settled(admin);
  await expect(rows).toHaveCount(200);
  await admin.locator('#view [data-size]').selectOption('0'); // «الكل»
  await settled(admin);
  await expect.poll(() => rows.count()).toBeGreaterThan(200);
});
