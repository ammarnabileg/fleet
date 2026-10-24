// The month imported from a file with the client's own column names: after the upload the panel shows the file's
// sheets and headers, a column chosen for each field, the first rows previewed as mapped, checked, applied; the next
// upload of the platform finds the same columns chosen.
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');
const { xlsx } = require('./xlsx');

const MONTH = new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 7); // Kuwait time
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const top = (page) => page.locator('.overlay[data-open]').last();
const day = (d) => `${MONTH}-${String(d).padStart(2, '0')}`;

test('a file with its own headers mapped to the fields, checked, applied, the mapping kept', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الربط ' + n, en: 'Mapping company ' + n } });
  const platform = await api.post('/payroll/platforms', { code: 'mp' + n, name: { ar: 'منصة الربط ' + n, en: 'Mapping ' + n }, daily_fields: [] });
  await api.put(`/payroll/platforms/${platform.id}/fields`, { version: 0, daily: [], monthly: [
    { key: 'batch_orders', builtin: 'batch_orders', type: 'batch_orders', label: { ar: 'الباتشات', en: 'Batches' } },
    { key: 'attendance_marks', builtin: 'attendance_marks', type: 'int', label: { ar: 'علامات X', en: 'Marks' } },
  ] });
  const driver = await api.post('/employees', {
    employee_number: 'MP' + n, name: { ar: 'سائق الربط ' + n, en: 'Mapping driver ' + n }, company_id: company.id, is_driver: true,
    phone: phone(), platform_id: platform.id, platform_driver_id: 'M' + n,
  });
  const file = xlsx({
    'غلاف': [['تقرير الشهر']],
    'البيانات': [
      ['كود المندوب', 'الفئة', 'من', 'إلى', 'التوصيلات', 'إكس'],
      ['M' + n, 2, day(1), day(7), 120, 1],
      ['M' + n, 1, day(8), day(14), 100, ''],
      ['M' + n, 2, day(15), day(21), 90, ''],
    ],
  });

  await admin.goto(`/admin.html#/platforms/${platform.id}?tab=import&month=${MONTH}`);
  await settled(admin);
  await admin.click('#mi-import');
  const d = top(admin);
  await d.locator('input[type=file]').setInputFiles({ name: 'month.xlsx', mimeType: XLSX, buffer: file });
  const map = d.locator('[data-mapping]');
  await expect(map).toBeVisible();
  await expect(d.locator('[data-map-sheet]')).toHaveCount(0); // the one sheet with headers is taken (the cover has none)
  await expect(d.locator('[data-map=period_start]')).toHaveValue('من'); // a header that names the field
  await expect(d.locator('[data-map=batch]')).toHaveValue(''); // the client's own name: chosen by hand
  await d.locator('[data-map=platform_driver_id]').selectOption('كود المندوب');
  await d.locator('[data-map=batch]').selectOption('الفئة');
  await d.locator('[data-map=period_end]').selectOption('إلى');
  await d.locator('[data-map=orders]').selectOption('التوصيلات');
  await d.locator('[data-map=attendance_marks]').selectOption('إكس');
  const preview = d.locator('[data-map-preview]');
  await expect(preview.locator('tbody tr')).toHaveCount(3);
  await expect(preview.locator('tbody tr').first()).toContainText('M' + n);
  await expect(preview.locator('tbody tr').first()).toContainText(day(1));

  await d.locator('button[type=submit]').click();
  const check = d.locator('[data-import-check]');
  await expect(check).toContainText('1 سائق');
  await expect(check).toContainText(`2:120@${day(1)}/${day(7)}`);
  await clearToasts(admin);
  await d.locator('[data-btn="2"]').click();
  await expect(admin.locator('.toast').last()).toContainText('طُبق الملف على 1 سائق');
  await settled(admin);
  const review = await api.get(`/payroll/month-review?platform_id=${platform.id}&month=${MONTH}-01`);
  const row = review.rows.find((r) => r.employee.id === driver.id);
  expect(row.batches.map((b) => [b.batch, b.orders, b.period_start])).toEqual([[2, 120, day(1)], [1, 100, day(8)], [2, 90, day(15)]]);
  expect(row.values).toEqual({ attendance_marks: '1.000' });

  // the next upload: the columns chosen last time are chosen again
  await admin.click('#mi-import');
  const d2 = top(admin);
  await d2.locator('input[type=file]').setInputFiles({ name: 'month.xlsx', mimeType: XLSX, buffer: file });
  await expect(d2.locator('[data-map=platform_driver_id]')).toHaveValue('كود المندوب');
  await expect(d2.locator('[data-map=period_end]')).toHaveValue('إلى');
  await d2.locator('button[type=submit]').click();
  await expect(d2.locator('[data-import-check]')).toContainText('نفسها الموجودة'); // never counted twice
});
