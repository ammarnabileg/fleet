// The payroll rules designer and the month around it: a platform's own fields set in the panel, the month's data
// imported from the partner's batch report (checked before it is applied, never counted twice), a driver's month
// corrected with an approved exception, and the six stages of the month.
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');
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
  // a corrected report: refused until «استبدال الشهر كله» is chosen, then the month's batch rows are the file's
  const corrected = xlsx({ Riders: [['Rider ID', 'Batch No.', 'Total Completed Deliveries'], ['R' + s.n + '1', 4, 120], ['R' + s.n + '1', 2, 39], ['R' + s.n + '2', 1, 200]] });
  await admin.click('#mi-import');
  const d2 = top();
  await d2.locator('input[type=file]').setInputFiles({ name: 'corrected.xlsx', mimeType: XLSX, buffer: corrected });
  await d2.locator('button[type=submit]').click();
  await expect(d2.locator('[data-reason=month_has_batches]')).toBeVisible();
  await expect(d2.locator('[data-btn="2"]')).toBeDisabled();
  await d2.locator('[name=replace_month]').check();
  await d2.locator('button[type=submit]').click();
  await expect(d2.locator('[data-reasons]')).toHaveCount(0);
  await clearToasts(admin);
  await d2.locator('[data-btn="2"]').click();
  await expect(admin.locator('.toast').last()).toContainText('طُبق الملف على 2 سائق');
  await settled(admin);
  const review = await api.get(`/payroll/month-review?platform_id=${s.platform.id}&month=${MONTH}-01`);
  const a = review.rows.find((r) => r.employee.id === s.a.id);
  expect(a.batches).toEqual([{ batch: 2, orders: 39 }, { batch: 4, orders: 120 }]);
  expect(a.missing).toEqual(['attendance_marks']);
  await expect(admin.locator(`[data-mrow="${s.a.id}"]`)).toContainText('2:39');

  // ---- his month corrected in review, and an approved exception with its note
  await admin.click(`[data-mrow="${s.a.id}"]`);
  const dr = top();
  await expect(dr.locator('[data-missing]')).toContainText('علامات الحضور');
  await dr.locator('[name=batches]').fill('2:39, 4-120'); // a malformed entry is said, never dropped
  await clearToasts(admin);
  await dr.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.toast').last()).toContainText('باتش:طلبات');
  await dr.locator('[name=batches]').fill('2:39, 4:120');
  await dr.locator('[name=v_attendance_marks]').fill('2');
  await clearToasts(admin);
  await dr.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظت بيانات الشهر');
  await settled(admin);
  await admin.click(`[data-mrow="${s.a.id}"]`);
  await top().getByRole('button', { name: 'استثناء' }).click();
  const x = top();
  await x.locator('input[name=kind][value=exception_day]').check({ force: true });
  await x.locator('[name=ex_valid_days]').check();
  await x.locator('[name=days]').fill('2');
  await x.locator('[name=note]').fill('يومان بعذر طبي');
  await clearToasts(admin);
  await x.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('اعتُمد الاستثناء');
  await settled(admin);
  const after = (await api.get(`/payroll/month-review?platform_id=${s.platform.id}&month=${MONTH}-01`)).rows.find((r) => r.employee.id === s.a.id);
  expect([after.values, after.exceptions.map((e) => [e.kind, e.days, e.excuses, e.note]), after.missing]).toEqual([
    { attendance_marks: '2.000' }, [['exception_day', 2, ['valid_days'], 'يومان بعذر طبي']], [],
  ]);
});

test('a scheme from a template in the rules designer: reordered, a rule added, tried, saved, and the month computed', async ({ admin, api }) => {
  const s = await setup(api);
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- from the Keeta as-paid template
  await admin.goto('/admin.html#/payroll?tab=schemes');
  await settled(admin);
  await admin.click(`[data-new="${s.platform.id}"]`);
  const m = top();
  await expect(m.locator('[data-templates]')).toContainText('قيم أولية تحتاج تأكيد'); // the plan-document ones
  await m.locator('[name=code]').fill('paid');
  await m.locator('[name=name_ar]').fill('كما صُرف ' + s.n);
  await m.locator('[name=name_en]').fill('As paid ' + s.n);
  await m.locator('input[name=template][value=keeta_paid]').check({ force: true });
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('أُنشئ النظام');
  const scheme = (await api.get('/payroll/schemes')).find((x) => x.platform_id === s.platform.id);
  expect([scheme.calculator, scheme.designed, scheme.blocks.map((b) => b.type)]).toEqual(['blocks', true,
    ['fixed_salary', 'target_overage', 'attendance_marks', 'star_day', 'special_day_violation']]);

  // ---- the designer: blocks in their order, one moved, one added from the palette with a condition
  await admin.locator(`[data-scheme="${scheme.id}"]`).click();
  await settled(admin);
  const blocks = admin.locator('[data-blocks] [data-block]');
  await expect(blocks).toHaveCount(5);
  await admin.click('[data-down="2"]'); // the marks after the star day
  await expect(blocks.nth(3)).toContainText('مخالفات الحضور');
  await admin.click('#ds-add');
  await top().locator('[data-pick=monthly_bonus]').click();
  const f = top();
  await f.locator('[name=p_amount]').fill('25');
  await f.locator('[data-c-add]').click();
  await f.locator('[data-c-fact="0"]').selectOption('orders');
  await f.locator('[data-c-op="0"]').selectOption('gte');
  await f.locator('[data-c-value="0"]').fill('600');
  await f.locator('button[type=submit]').click();
  await expect(blocks).toHaveCount(6);
  await expect(blocks.nth(5)).toContainText('الطلبات لا يقل عن 600');

  // ---- «جرّب»: each line and its formula, the net
  const tryBox = admin.locator('[data-try]');
  await tryBox.locator('[name=s_orders]').fill('603');
  await tryBox.locator('[name=s_attendance_marks]').fill('1');
  await tryBox.locator('[name=s_star]').selectOption('false');
  await tryBox.locator('[name=s_basic_salary]').fill('200');
  await tryBox.locator('[data-try-run]').click();
  await expect(tryBox.locator('[data-try-lines]')).toContainText('(603 − 310) × 0.500 = 146.500');
  await expect(tryBox.locator('[data-try-net]')).toContainText('351.500'); // 200 + 146.5 - 20 + 25

  // ---- saved (nobody paid on it yet: redefined)
  await admin.click('#ds-save');
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظت النسخة');
  const d = await api.get(`/payroll/schemes/${scheme.id}/designer`);
  expect(d.versions[0].blocks.map((b) => b.type)).toEqual(['fixed_salary', 'target_overage', 'star_day', 'attendance_marks', 'special_day_violation', 'monthly_bonus']);

  // ---- assigned, the month's figures, the run: the line explains itself
  await api.post(`/payroll/schemes/${scheme.id}/assign`, { employee_ids: [s.a.id], month: MONTH + '-01' });
  await api.post('/payroll/statements', { employee_id: s.a.id, month: MONTH + '-01', orders: 603 });
  await api.put(`/payroll/month-review/${s.a.id}`, { month: MONTH + '-01', values: { attendance_marks: 1, star_day_failed: false } });
  const version = (await api.get('/settings')).payroll.version;
  await api.put('/settings/payroll', { version, value: { max_deduction_percent: '50.00', deduction_cap_base: 'gross' } });
  const run = await api.post('/payroll/runs', { company_id: s.company.id, month: MONTH + '-01' });
  const line = run.lines.find((x) => x.employee.id === s.a.id);
  expect([line.gross, line.net, line.flags]).toEqual(['371.500', '351.500', []]);
  await admin.goto('/admin.html#/payroll/run/' + run.id);
  await settled(admin);
  await admin.locator(`[data-line="${s.a.id}"]`).first().click();
  await expect(top()).toContainText('مكافأة تجاوز التارجت');
  await expect(top()).toContainText('(603 − 310) × 0.500 = 146.500');
  await admin.keyboard.press('Escape');

  // ---- a personal rate on a scheme that does not use one: said in the dialog before saving
  await admin.goto('/admin.html#/employees');
  await settled(admin);
  await search(admin, s.b.employee_number);
  await admin.locator('#view tbody tr', { hasText: s.b.employee_number }).click();
  await top().locator('[data-scheme-box] [data-scheme-set]').click();
  const as = top();
  await as.locator('[name=scheme]').selectOption(scheme.id);
  await as.locator('[name=personal_rate]').fill('0.800');
  await expect(as.locator('[data-rate-warning]')).toBeVisible();
  await as.locator('[name=personal_rate]').fill('');
  await expect(as.locator('[data-rate-warning]')).toBeHidden();
});
