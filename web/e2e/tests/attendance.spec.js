// Absence and leave from the panel: a new driver's days without a start of day classified, two at once and one alone;
// a leave registered pending then approved, an overlapping one refused; a classification taken off brings its day back.
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');

const day = (back) => new Date(Date.now() + 3 * 3600e3 - back * 86400e3).toISOString().slice(0, 10); // Kuwait date

test('days classified, a leave approved, an overlap refused, a classification taken off', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الغياب ' + n, en: 'Absence company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'D' + uid(), name: { ar: 'سائق الغياب ' + n, en: 'Absence driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(), hire_date: day(3),
  });
  const name = driver.name.ar;
  const top = () => admin.locator('.overlay[data-open]').last();
  const span = `date_from=${day(5)}&date_to=${day(0)}&employee_id=${driver.id}`;
  const days = async () => (await api.get('/attendance/days?' + span)).days.map((x) => x.day);
  expect(await days()).toEqual([day(1), day(2), day(3)]); // hired three days ago, never started a day

  // ---- the first tab: his three days; two classified absent at once
  await admin.goto('/admin.html#/attendance');
  await settled(admin);
  await search(admin, name);
  const rows = admin.locator('#view tbody tr', { hasText: name });
  await expect(rows).toHaveCount(3);
  await rows.nth(0).locator('input[type=checkbox]').check();
  await rows.nth(1).locator('input[type=checkbox]').check();
  await admin.getByRole('button', { name: 'تصنيف المحدد' }).click();
  await top().locator('[name=kind]').selectOption('absence');
  await top().locator('[name=note]').fill('لم يرد على الهاتف');
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('صُنّف 2 يوم');
  await expect(rows).toHaveCount(1);
  // the last one alone, from its row: a rest day
  await rows.click();
  await top().locator('[name=kind]').selectOption('rest');
  await top().locator('button[type=submit]').click();
  await expect(rows).toHaveCount(0);
  expect(await days()).toEqual([]);
  const marks = await api.get('/attendance/marks?' + span);
  expect(marks.map((m) => [m.day, m.kind, m.note])).toEqual([
    [day(1), 'absence', 'لم يرد على الهاتف'], [day(2), 'absence', 'لم يرد على الهاتف'], [day(3), 'rest', null],
  ]);

  // ---- a sick leave from tomorrow, registered pending, then approved from its drawer
  await admin.locator('#view [role=tab]', { hasText: 'الإجازات' }).click();
  await settled(admin);
  await admin.getByRole('button', { name: 'تسجيل إجازة' }).click();
  const m = top();
  const label = await m.locator('[name=employee]').evaluate((el, num) => [...el.list.options].map((o) => o.value).find((v) => v.startsWith(num + ' ')), driver.employee_number);
  await m.locator('[name=employee]').fill(label);
  await m.locator('[name=kind]').selectOption('sick');
  await m.locator('[name=from]').fill(day(-1));
  await m.locator('[name=to]').fill(day(-3));
  await m.locator('[name=approve]').uncheck();
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('بانتظار الاعتماد');
  const pending = admin.locator('#view [data-panel=leaves] tbody tr', { hasText: name });
  await expect(pending).toContainText('مرضية');
  await expect(pending).toContainText('3');
  await pending.click();
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click(); // the drawer's
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click(); // the confirmation's, on top of it
  await expect(pending).toHaveCount(0); // no longer waiting
  await expect(top()).toContainText('معتمدة'); // its drawer opens again, as it is now
  await admin.keyboard.press('Escape');
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);
  const leaves = await api.get('/leaves?employee_id=' + driver.id);
  expect(leaves.map((x) => [x.kind, x.status, x.date_from, x.date_to, x.days])).toEqual([['sick', 'approved', day(-1), day(-3), 3]]);

  // ---- an overlapping leave is refused with its reason
  await admin.getByRole('button', { name: 'تسجيل إجازة' }).click();
  const m2 = top();
  await m2.locator('[name=employee]').fill(label);
  await m2.locator('[name=from]').fill(day(-3));
  await m2.locator('[name=to]').fill(day(-4));
  admin.allow(/HTTP 409 POST \S+\/api\/v1\/leaves$/); // the overlap, refused
  await clearToasts(admin);
  await m2.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('إجازة أخرى في بعض هذه الأيام');
  await admin.keyboard.press('Escape');

  // ---- the third tab: the rest day's classification taken off, and the day is listed again
  await admin.locator('#view [role=tab]', { hasText: 'الأيام المصنفة' }).click();
  await settled(admin);
  await search(admin, name, '#view [data-panel=marks]');
  const marked = admin.locator('#view [data-panel=marks] tbody tr', { hasText: name });
  await expect(marked).toHaveCount(3);
  await marked.filter({ hasText: 'يوم راحة' }).locator('[data-row-menu]').click();
  await admin.getByRole('menuitem', { name: 'إلغاء التصنيف' }).click();
  await admin.locator('.overlay[data-open]').last().getByRole('button', { name: 'إلغاء التصنيف' }).click();
  await expect(marked).toHaveCount(2);
  expect(await days()).toEqual([day(3)]);
});
