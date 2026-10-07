// Pay schemes from end to end in the panel: a tiered scheme built in the form, drivers put on schemes from their file
// and from the list, a driver's request from his phone approved in the queue, the month's figures his scheme needs,
// and the payroll line, the approval and the payslip explaining the month.
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');

const MONTH = new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 7); // Kuwait time
const IBAN = 'KW81CBKU0000000000001234560101';

async function setup(api) {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الأنظمة ' + n, en: 'Schemes company ' + n } });
  const keeta = await api.post('/payroll/platforms', { code: 'k' + n, name: { ar: 'كيتا ' + n, en: 'Keeta ' + n } });
  const talabat = await api.post('/payroll/platforms', { code: 't' + n, name: { ar: 'طلبات ' + n, en: 'Talabat ' + n } });
  const driver = (name, platform) => api.post('/employees', {
    employee_number: 'E' + uid(),
    name: { ar: name + ' ' + n, en: 'Driver ' + n },
    company_id: company.id,
    is_driver: true,
    phone: phone(),
    basic_salary: '300.000',
    iban: IBAN,
    payment_method: 'bank',
    platform_id: platform.id,
  });
  return {
    n, company, keeta, talabat,
    bilal: await driver('بلال', keeta),
    faisal: await driver('فيصل', talabat),
  };
}

test('pay schemes: built, assigned, asked for, approved, and the month explained', async ({ admin, api }) => {
  const s = await setup(api);
  // the dialog in front; one closing behind it (a short animation) is no longer "open"
  const top = () => admin.locator('.overlay[data-open]').last();
  const submit = () => top().locator('button[type=submit]').click();

  // ---- the Keeta scheme from the form, every step from the steps editor
  await admin.goto('/admin.html#/payroll?tab=schemes');
  await settled(admin);
  await admin.click(`[data-new="${s.keeta.id}"]`);
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(1); // one form, whatever happened before the click
  const m = top();
  await m.locator('[name=code]').fill('base');
  await m.locator('[name=name_ar]').fill('كيتا الأساسي');
  await m.locator('[name=name_en]').fill('Keeta base');
  await m.locator('[name=calculator]').selectOption('tiered_target');
  await m.locator('[name=per_order]').fill('0.350');
  await m.locator('[name=reduced_rate]').fill('0.200');
  await m.locator('[name=missing_order_rate]').fill('0.350');
  const steps = [
    ['tier_bonus', 450, '50'], ['tier_bonus', 540, '90'], ['tier_bonus', 620, '130'], ['tier_bonus', 710, '200'],
    ['marks_deduction', 3, '10'], ['marks_deduction', 4, '30'], ['marks_reduce', 5, null],
  ];
  for (const [i, [kind, from, amount]] of steps.entries()) {
    await m.locator('[data-step-add]').click();
    await m.locator(`[data-step-k="${i}"]`).selectOption(kind);
    await m.locator(`[data-step-t="${i}"]`).fill(String(from));
    if (amount != null) await m.locator(`[data-step-a="${i}"]`).fill(amount);
    else await expect(m.locator(`[data-step-a="${i}"]`)).toBeDisabled(); // the reduced price applies
  }
  await m.locator('[name=cover_maintenance]').check();
  await submit();
  await expect(top()).toBeHidden();
  const keeta = (await api.get('/payroll/schemes')).find((x) => x.platform_id === s.keeta.id);
  expect(keeta).toMatchObject({
    calculator: 'tiered_target', per_order: '0.350', reduced_rate: '0.200', missing_order_rate: '0.350',
    company_covers: ['maintenance'], bonus_when_reduced: false, marks_when_reduced: false, floor_at_zero: true,
  });
  expect(keeta.steps.map((x) => [x.kind, Number(x.threshold), x.amount])).toEqual([
    ['marks_deduction', 3, '10.000'], ['marks_deduction', 4, '30.000'], ['marks_reduce', 5, null],
    ['tier_bonus', 450, '50.000'], ['tier_bonus', 540, '90.000'], ['tier_bonus', 620, '130.000'], ['tier_bonus', 710, '200.000'],
  ]);

  // ---- Talabat's two by the API; the cards show each scheme's terms
  const fixed = await api.post('/payroll/schemes', {
    platform_id: s.talabat.id, code: 'fixed', name: { ar: 'سعر ثابت 0.350', en: 'Fixed 0.350' },
    calculator: 'per_order', per_order: '0.350', company_covers: ['maintenance', 'housing', 'gas', 'sim'],
  });
  const batch = await api.post('/payroll/schemes', {
    platform_id: s.talabat.id, code: 'batch', name: { ar: 'نظام الباتش', en: 'Batch' }, calculator: 'batch',
    steps: [['1', '0.700'], ['2', '0.675'], ['3', '0.600'], ['4', '0.525'], ['5', '0.400']]
      .map(([level, rate]) => ({ kind: 'batch_rate', threshold: level, amount: rate })),
  });
  await admin.reload();
  await settled(admin);
  const card = admin.locator(`[data-scheme="${keeta.id}"]`);
  await expect(card).toContainText('540 طلب: 90.000');
  await expect(card).toContainText('5 علامات فأكثر: كل الطلبات بالسعر المخفض');
  await expect(admin.locator(`[data-scheme="${batch.id}"]`)).toContainText('باتش 5: 0.400');

  // ---- Bilal from his file
  await admin.goto('/admin.html#/employees');
  await settled(admin);
  await search(admin, s.bilal.employee_number);
  await admin.locator('#view tbody tr', { hasText: s.bilal.employee_number }).click();
  const box = top().locator('[data-scheme-box]');
  await expect(box).toContainText('لا نظام');
  await box.locator('[data-scheme-set]').click();
  await top().locator('[name=scheme]').selectOption(keeta.id);
  await submit();
  await expect(box).toContainText('كيتا الأساسي');
  await admin.keyboard.press('Escape');

  // ---- Faisal from the list: selected, then "pay scheme"
  await admin.goto('/admin.html#/employees');
  await settled(admin);
  await search(admin, s.faisal.employee_number);
  await admin.locator('#view tbody tr', { hasText: s.faisal.employee_number }).locator('input[type=checkbox]').check();
  await admin.getByRole('button', { name: 'نظام الدفع', exact: true }).click();
  await top().locator('[name=scheme]').selectOption(fixed.id);
  await clearToasts(admin); // Bilal's toast, the same words, is still up
  await submit();
  await expect(admin.locator('.toast').last()).toContainText('نظام الدفع لـ 1 سائق');
  const faisalHistory = await api.get(`/employees/${s.faisal.id}/schemes`);
  expect(faisalHistory.map((x) => [x.scheme.code, x.valid_from, x.source])).toEqual([['fixed', MONTH + '-01', 'office']]);

  // ---- Faisal asks from his phone for the batch scheme; the office approves it in the queue
  const faisalPhone = await api.driverPhone(s.faisal.id, 'e2e-' + s.n + '-faisal');
  const view = await faisalPhone.call('GET', '/driver/schemes');
  expect(view.schemes.map((x) => x.code).sort()).toEqual(['batch', 'fixed']);
  expect(view.schemes[0]).not.toHaveProperty('drivers');
  await faisalPhone.call('POST', '/driver/scheme-requests', { scheme_id: batch.id, note: 'عاوز الباتش' });
  await admin.evaluate(() => window.BT.A.refreshCounts());
  await expect(admin.locator('.nav-item[href="#/payroll"] .count')).toBeVisible();
  await admin.goto('/admin.html#/payroll?tab=requests');
  await settled(admin);
  await admin.locator('[data-p=requests] tbody tr', { hasText: s.faisal.name.ar }).click();
  await expect(top()).toContainText('يطلب: نظام الباتش');
  await expect(top()).toContainText('عاوز الباتش');
  await top().getByRole('button', { name: 'موافقة' }).click();
  await expect(top()).toBeHidden();
  const after = await faisalPhone.call('GET', '/driver/schemes');
  expect([after.request.status, after.next_month.code, after.current.code]).toEqual(['approved', 'batch', 'fixed']);

  // ---- the month: Bilal's statement asks for marks and the star day only; the reviewer corrects the marks
  for (const [who, figures] of [[s.bilal, { orders: 560, attendance_marks: 2, star_day_failed: false }], [s.faisal, { orders: 300 }]]) {
    await api.post('/payroll/statements', Object.assign({ employee_id: who.id, month: MONTH + '-01' }, figures));
  }
  await admin.goto('/admin.html#/payroll?tab=statements');
  await settled(admin);
  await admin.locator('[data-p=statements] .chip', { hasText: 'المعتمدة' }).click();
  await admin.locator('[data-p=statements] tbody tr', { hasText: s.bilal.name.ar }).click();
  const st = top();
  await expect(st).toContainText('نظام الدفع: كيتا الأساسي');
  await expect(st.locator('[name=attendance_marks]')).toHaveValue('2');
  await expect(st.locator('[name=star_day_failed]')).toHaveValue('false');
  await expect(st.locator('[name=batch_level]')).toHaveCount(0); // not his scheme's figure
  await st.locator('[name=attendance_marks]').fill('3');
  await st.getByRole('button', { name: 'حفظ التصحيح' }).click();
  await expect(st).toBeHidden();
  const saved = (await api.get(`/payroll/statements?month=${MONTH}-01&status=approved&limit=500`))
    .find((x) => x.employee.id === s.bilal.id);
  expect([saved.orders, saved.attendance_marks, saved.star_day_failed]).toEqual([560, 3, false]);

  // ---- the run: 560 x 0.350 = 196, the 540 tier 90, 3 marks -10: 286 earned, 276 net; then approved
  const version = (await api.get('/settings')).payroll.version;
  await api.put('/settings/payroll', { version, value: { max_deduction_percent: '50.00', deduction_cap_base: 'gross' } });
  const run = await api.post('/payroll/runs', { company_id: s.company.id, month: MONTH + '-01' });
  await admin.goto('/admin.html#/payroll/run/' + run.id);
  await settled(admin);
  await admin.locator(`[data-line="${s.bilal.id}"]`).first().click();
  const line = top();
  await expect(line).toContainText('حساب نظام الدفع — كيتا الأساسي');
  await expect(line).toContainText('560 طلب × 0.350');
  await expect(line).toContainText('وصل 560 طلب: شريحة 540');
  await expect(line).toContainText('3 علامات حضور');
  await admin.keyboard.press('Escape');
  await admin.click('#run-approve');
  await admin.getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect.poll(async () => (await api.get('/payroll/runs/' + run.id)).status).toBe('approved');
  const lines = (await api.get('/payroll/runs/' + run.id)).lines;
  const bilal = lines.find((x) => x.employee.id === s.bilal.id);
  expect([bilal.gross, bilal.deductions, bilal.net]).toEqual(['286.000', '10.000', '276.000']);
  expect(lines.find((x) => x.employee.id === s.faisal.id).gross).toBe('105.000'); // 300 x 0.350, this month still fixed

  // ---- his payslip in the app says the same, item by item
  const bilalPhone = await api.driverPhone(s.bilal.id, 'e2e-' + s.n + '-bilal');
  const slip = (await bilalPhone.call('GET', '/driver/payslips'))[0];
  expect(slip.breakdown.map((b) => [b.code, b.amount])).toEqual([
    ['orders_pay', '196.000'], ['tier_bonus', '90.000'], ['marks_deduction', '-10.000'],
  ]);
});
