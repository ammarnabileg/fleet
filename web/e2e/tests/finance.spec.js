// Finance from the panel: a fuel expense for a vehicle registered and approved; the entries generated, its draft
// approved with its lines, then reversed; the export carries both; the trial balance adds up to zero; the vehicle's file
// lists the expense; an account added to the chart.
const fs = require('fs');
const { test, expect, uid, settled, clearToasts } = require('./fixtures');
const { readXlsx } = require('./xlsx');

test('an expense from registration to its entry, reversed, exported, and the books still balance', async ({ admin, api }) => {
  test.setTimeout(150_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المالية ' + n, en: 'Finance company ' + n } });
  const vehicle = await api.post('/vehicles', { company_id: company.id, plate_number: 'F' + n, make: 'Toyota', model: 'Yaris', last_odometer_km: 1000 });
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- registered with its vehicle, 40 litres for 12.500
  await admin.goto('/admin.html#/finance');
  await settled(admin);
  await admin.getByRole('button', { name: 'تسجيل مصروف' }).click();
  const m = top();
  await m.locator('[name=company]').selectOption(String(company.id));
  await m.locator('[name=type]').selectOption({ label: 'وقود' });
  await m.locator('[name=amount]').fill('12.5');
  await m.locator('[name=quantity]').fill('40');
  const label = await m.locator('[name=vehicle]').evaluate((el, p) => [...el.list.options].map((o) => o.value).find((v) => v.includes(p)), 'F' + n);
  await m.locator('[name=vehicle]').fill(label);
  await m.locator('[name=supplier]').fill('محطة ' + n);
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('سُجّل المصروف #');
  const number = (await admin.locator('.toast').last().innerText()).match(/#(\d+)/)[1];
  const row = admin.locator('#view [data-panel=expenses] tbody tr', { hasText: '#' + number });
  await expect(row).toContainText('12.500');
  await expect(row).toContainText('F' + n);

  // ---- approved from its drawer
  await row.click();
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click(); // the confirmation
  await expect(top()).toContainText('معتمد');
  await admin.keyboard.press('Escape');
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  // ---- the entries: generated, the expense's draft approved with its two lines
  await admin.locator('#view [role=tab]', { hasText: 'القيود' }).click();
  await settled(admin);
  await admin.locator('#view [data-post]').click();
  await expect(top()).toContainText('أُنشئت');
  await top().getByRole('button', { name: 'إغلاق', exact: true }).last().click();
  const draft = admin.locator('#view [data-panel=entries] tbody tr', { hasText: 'EXP-' + number });
  await expect(draft).toContainText('مسودة');
  await draft.click();
  const lines = top().locator('tbody tr');
  await expect(lines).toHaveCount(2);
  await expect(lines.nth(0)).toContainText('5104');
  await expect(lines.nth(0)).toContainText('12.500');
  await expect(lines.nth(1)).toContainText('1101');
  await clearToasts(admin);
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('اعتُمد القيد');
  await expect(draft).toHaveCount(0); // no longer among the drafts

  // ---- reversed with a reason: the mirror image, approved
  await admin.locator('#view [data-panel=entries] [data-chip=approved]').click();
  const approved = admin.locator('#view [data-panel=entries] tbody tr', { hasText: 'EXP-' + number });
  await expect(approved).toHaveCount(1);
  await approved.click();
  await top().getByRole('button', { name: 'قيد عكسي' }).click();
  await top().locator('[name=reason]').fill('مصروف مسجل مرتين');
  await clearToasts(admin);
  await top().getByRole('button', { name: 'عكس القيد' }).click();
  await expect(admin.locator('.toast').last()).toContainText('أُنشئ القيد العكسي');
  await expect(admin.locator('#view [data-panel=entries] tbody tr', { hasText: 'EXP-' + number })).toHaveCount(2);

  // ---- exported: both, with their debits and credits
  const [file] = await Promise.all([admin.waitForEvent('download'), admin.locator('#view [data-export=xlsx]').click()]);
  const sheet = readXlsx(fs.readFileSync(await file.path()));
  expect(sheet[0].slice(0, 6)).toEqual(['رقم القيد', 'التاريخ', 'رمز الحساب', 'اسم الحساب', 'مدين', 'دائن']);
  const mine = sheet.filter((r) => r.includes('EXP-' + number));
  expect(mine.length).toBe(4); // two lines each
  expect(mine.map((r) => r[2]).sort()).toEqual(['1101', '1101', '5104', '5104']);

  // ---- the trial balance adds up to zero
  await admin.locator('#view [role=tab]', { hasText: 'ميزان المراجعة' }).click();
  await settled(admin);
  await expect(admin.locator('[data-tb-total]')).toHaveText('0.000');

  // ---- the vehicle's file lists it
  await admin.goto('/admin.html#/vehicles/' + vehicle.id);
  await settled(admin);
  await expect(admin.locator('#veh-expenses')).toContainText('#' + number);

  // ---- the accountant's own account added to the chart
  await admin.goto('/admin.html#/finance?tab=chart');
  await settled(admin);
  await admin.locator('[data-acc-new]').click();
  const code = String(7000 + (Number(n) % 1000));
  await top().locator('[name=code]').fill(code);
  await top().locator('[name=type]').selectOption('expense');
  await top().locator('[name=name_ar]').fill('حساب ' + n);
  await top().locator('[name=name_en]').fill('Account ' + n);
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظ الحساب');
  await expect(admin.locator('#view [data-acc]', { hasText: 'حساب ' + n })).toContainText(code);
});
