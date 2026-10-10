// The payroll rules designer and the month around it: a platform's own fields set in the panel, the month's data
// imported from the partner's batch report (checked before it is applied, never counted twice), a driver's month
// corrected with an approved exception, and the six stages of the month.
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');
const { xlsx } = require('./xlsx');

const MONTH = new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 7); // Kuwait time
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

async function setup(api) {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المصمم ' + n, en: 'Designer company ' + n } });
  const platform = await api.post('/payroll/platforms', { code: 'dz' + n, name: { ar: 'منصة المصمم ' + n, en: 'Designer ' + n }, daily_fields: ['orders', 'cash'] });
  const driver = (i) => api.post('/employees', {
    employee_number: 'DZ' + n + i, name: { ar: 'سائق المصمم ' + n + ' ' + i, en: 'Designer driver ' + n + ' ' + i },
    company_id: company.id, is_driver: true, phone: phone(), basic_salary: '200.000', payment_method: 'cash',
    platform_id: platform.id, platform_driver_id: 'R' + n + i,
  });
  return { n, company, platform, a: await driver(1), b: await driver(2) };
}

test('a platform\'s own fields, the month imported and checked, a driver\'s month with an exception', async ({ admin, api }) => {
  const s = await setup(api);
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- the platform's fields: a daily field of its own, and the monthly batch rows and marks
  await admin.goto('/admin.html#/payroll?tab=platforms');
  await settled(admin);
  await admin.click(`[data-fields="${s.platform.id}"]`);
  const m = top();
  await expect(m.locator('[data-ftable=daily] tbody tr')).toHaveCount(2); // orders and cash, as its daily_fields say
  admin.once('dialog', (d) => d.accept('Grocery orders'));
  await m.locator('[data-fadd="daily:custom"]').click();
  await expect(m.locator('[data-ftable=daily] tbody tr')).toHaveCount(3);
  await m.locator('[data-fl-ar="daily:2"]').fill('طلبات البقالة');
  await m.locator('[name=freq_daily_2]').check();
  await m.locator('[data-fadd="monthly:batch_orders"]').click();
  await m.locator('[data-fadd="monthly:attendance_marks"]').click();
  await m.locator('[name=freq_monthly_1]').check();
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظت الحقول');
  const fields = await api.get(`/payroll/platforms/${s.platform.id}/fields`);
  expect(fields.daily.map((f) => [f.key, f.type, f.required])).toEqual([['orders', 'int', true], ['cash', 'money', true], ['grocery_orders', 'int', true]]);
  expect(fields.monthly.map((f) => f.key)).toEqual(['batch_orders', 'attendance_marks']);

  // ---- the month: the partner's report checked, then applied; again: replaced, never added
  await admin.goto(`/admin.html#/payroll?tab=month&platform=${s.platform.id}&month=${MONTH}`);
  await settled(admin);
  await expect(admin.locator('[data-stepper] [data-stage]')).toHaveCount(6);
  await expect(admin.locator('[data-month-grid] tbody tr')).toHaveCount(2);
  const report = xlsx({ Riders: [
    ['Rider ID', 'Batch No.', 'Total Completed Deliveries'],
    ['R' + s.n + '1', 4, 118], ['R' + s.n + '1', 2, 39], ['R' + s.n + '2', 1, 200], ['R' + s.n + '2', 1, 200], ['NOBODY', 3, 10],
  ] });
  for (const round of [1, 2]) {
    await admin.click('#mi-import');
    const d = top();
    await d.locator('input[type=file]').setInputFiles({ name: 'partner.xlsx', mimeType: XLSX, buffer: report });
    await d.locator('button[type=submit]').click();
    const check = d.locator('[data-import-check]');
    await expect(check).toContainText('2 سائق');
    await expect(check).toContainText('NOBODY');
    await expect(check).toContainText('نفس الرقم، يُحسب مرة');
    if (round === 2) await expect(check).toContainText('استورد هذا الملف من قبل');
    await clearToasts(admin);
    await d.locator('[data-btn="2"]').click();
    await expect(admin.locator('.toast').last()).toContainText('طُبق الملف على 2 سائق');
    await settled(admin);
  }
  const review = await api.get(`/payroll/month-review?platform_id=${s.platform.id}&month=${MONTH}-01`);
  const a = review.rows.find((r) => r.employee.id === s.a.id);
  expect(a.batches).toEqual([{ batch: 2, orders: 39 }, { batch: 4, orders: 118 }]);
  expect(a.missing).toEqual(['attendance_marks']);
  await expect(admin.locator(`[data-mrow="${s.a.id}"]`)).toContainText('2:39');

  // ---- his month corrected in review, and an approved exception with its note
  await admin.click(`[data-mrow="${s.a.id}"]`);
  const dr = top();
  await dr.locator('[name=v_attendance_marks]').fill('2');
  await clearToasts(admin);
  await dr.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظت بيانات الشهر');
  await settled(admin);
  await admin.click(`[data-mrow="${s.a.id}"]`);
  await top().getByRole('button', { name: 'استثناء' }).click();
  const x = top();
  await x.locator('input[name=kind][value=exception_day]').check({ force: true });
  await x.locator('[name=days]').fill('2');
  await x.locator('[name=note]').fill('يومان بعذر طبي');
  await clearToasts(admin);
  await x.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('اعتُمد الاستثناء');
  await settled(admin);
  const after = (await api.get(`/payroll/month-review?platform_id=${s.platform.id}&month=${MONTH}-01`)).rows.find((r) => r.employee.id === s.a.id);
  expect([after.values, after.exceptions.map((e) => [e.kind, e.days, e.note]), after.missing]).toEqual([
    { attendance_marks: '2.000' }, [['exception_day', 2, 'يومان بعذر طبي']], [],
  ]);
});
