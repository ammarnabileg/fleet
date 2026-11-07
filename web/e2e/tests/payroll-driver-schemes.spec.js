// The office's page of every driver's pay scheme: who has none, who asked to change, and the office setting or
// changing a driver's scheme from a month, unasked, one driver or several at once, with only his company's schemes.
const { test, expect, uid, phone, settled, search } = require('./fixtures');

test('the office sets a driver\'s scheme and changes several at once, unasked', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة أنظمة السواقين ' + n, en: 'Driver schemes ' + n } });
  const plat = await api.post('/payroll/platforms', { code: 'ds' + n, name: { ar: 'منصة ' + n, en: 'Platform ' + n } });
  const other = await api.post('/payroll/platforms', { code: 'do' + n, name: { ar: 'أخرى ' + n, en: 'Other ' + n } });
  const tpl = (p, template, code) => api.post('/payroll/schemes/from-template', { platform_id: p.id, template, code, name: { ar: code, en: code } });
  const s350 = await tpl(plat, 'talabat_fixed_350', 'p350' + n);
  const s550 = await tpl(plat, 'talabat_fixed_550', 'p550' + n);
  const foreign = await tpl(other, 'talabat_fixed_680', 'o680' + n);
  const driver = (name) => api.post('/employees', {
    employee_number: 'DS' + uid(), name: { ar: name + ' ' + n, en: name + ' ' + n }, company_id: company.id,
    is_driver: true, phone: phone(), platform_id: plat.id,
  });
  const a = await driver('أحمد'), b = await driver('بدر'), c = await driver('جاسم');

  await admin.goto('/admin.html#/payroll?tab=drivers&platform=' + plat.id);
  await settled(admin);
  const panel = admin.locator('[data-p=drivers]');
  const row = (d) => panel.locator('tbody tr', { hasText: d.employee_number });
  await expect(row(a)).toContainText('بلا نظام');
  await expect(row(b)).toContainText('بلا نظام');

  // one driver, unasked: only his company's schemes are offered
  const top = () => admin.locator('.overlay[data-open]').last();
  await row(a).locator('[data-set-scheme]').click();
  const options = await top().locator('[name=scheme] option').allTextContents();
  expect(options.some((o) => o.includes('p350' + n))).toBe(true);
  expect(options.some((o) => o.includes(foreign.code))).toBe(false);
  await top().locator('[name=scheme]').selectOption(s350.id);
  await top().locator('button[type=submit]').click();
  await expect(row(a)).toContainText('p350' + n);

  // several at once
  await search(admin, 'DS', '[data-p=drivers]');
  for (const d of [b, c]) await row(d).locator('input[type=checkbox]').check();
  await panel.getByRole('button', { name: 'تغيير النظام' }).first().click();
  await top().locator('[name=scheme]').selectOption(s550.id);
  await top().locator('button[type=submit]').click();
  await expect(row(b)).toContainText('p550' + n);
  await expect(row(c)).toContainText('p550' + n);

  // «no scheme» lists only those still without one
  const left = await api.get('/payroll/driver-schemes?platform_id=' + plat.id + '&show=none');
  expect(left.items.map((x) => x.employee.id)).toEqual([]);
});
