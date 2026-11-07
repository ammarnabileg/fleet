// The client's payroll decisions in the panel: the reconciliation gate (a banner, and the approval refused until the
// owner turns it on), a driver's objection sent from his phone and answered in the panel, and a scheme's terms changed
// as a new version «يسري من» a later month.
const { test, expect, uid, phone, settled } = require('./fixtures');

const MONTH = new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 7); // Kuwait time
const IBAN = 'KW81CBKU0000000000001234560101';
const nextMonth = () => { const [y, m] = MONTH.split('-').map(Number); return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`; };
const top = (page) => page.locator('.overlay[data-open]').last();

async function setup(api) {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة القرارات ' + n, en: 'Decisions company ' + n } });
  const keeta = await api.post('/payroll/platforms', { code: 'q' + n, name: { ar: 'كيتا ' + n, en: 'Keeta ' + n } });
  const scheme = await api.post('/payroll/schemes', {
    platform_id: keeta.id, code: 'base', name: { ar: 'كيتا الأساسي ' + n, en: 'Keeta base ' + n }, calculator: 'tiered_target',
    per_order: '0.350', reduced_rate: '0.200', missing_order_rate: '0.350',
    steps: [{ kind: 'marks_deduction', threshold: 3, amount: '10' }, { kind: 'marks_reduce', threshold: 5, amount: null }],
  });
  const driver = await api.post('/employees', {
    employee_number: 'E' + uid(), name: { ar: 'سالم ' + n, en: 'Salem ' + n }, company_id: company.id, is_driver: true,
    phone: phone(), basic_salary: '300.000', iban: IBAN, payment_method: 'bank', platform_id: keeta.id,
  });
  await api.post(`/payroll/schemes/${scheme.id}/assign`, { employee_ids: [driver.id], month: MONTH + '-01' });
  await api.post('/payroll/statements', { employee_id: driver.id, month: MONTH + '-01', orders: 400, attendance_marks: 3, star_day_failed: false });
  const s = (await api.get('/settings')).payroll;
  await api.put('/settings/payroll', { version: s.version, value: Object.assign({}, s.value, { max_deduction_percent: '50.00', deduction_cap_base: 'gross' }) });
  const run = await api.post('/payroll/runs', { company_id: company.id, month: MONTH + '-01' });
  return { n, company, keeta, scheme, driver, run };
}

test('the reconciliation gate: a banner, and the approval refused until the owner turns it on', async ({ admin, api }) => {
  await api.payrollLive(false);
  try {
    const s = await setup(api);
    await admin.goto('/admin.html#/payroll?tab=runs');
    await settled(admin);
    await expect(admin.locator('[data-gate-banner]')).toContainText('اعتماد المسيرات متوقف لحد ما يتعمل اختبار المطابقة');
    await admin.goto('/admin.html#/payroll/run/' + s.run.id);
    await settled(admin);
    await expect(admin.locator('[data-gate-banner]')).toBeVisible();
    admin.allow(/HTTP 409 POST .*\/payroll\/runs\/.*\/approve/);
    await admin.click('#run-approve');
    await admin.getByRole('button', { name: 'اعتماد', exact: true }).click();
    await expect(admin.locator('.toast').last()).toContainText('فعّله من الإعدادات بعد المطابقة');
    expect((await api.get('/payroll/runs/' + s.run.id)).status).toBe('draft');

    // the owner turns it on in the settings; the banner goes and the run is approved
    await admin.goto('/admin.html#/settings?tab=system');
    await settled(admin);
    const sw = admin.locator('[data-owner-only="payroll.live_approval_enabled"] input');
    await expect(sw).toBeEnabled(); // the admin here is the owner
    await sw.check();
    await admin.locator('form[data-sec=payroll] [type=submit]').click();
    await expect.poll(async () => (await api.get('/payroll/gate')).live_approval_enabled).toBe(true);
    await admin.goto('/admin.html#/payroll/run/' + s.run.id);
    await settled(admin);
    await expect(admin.locator('[data-gate-banner]')).toHaveCount(0);
    await admin.click('#run-approve');
    await admin.getByRole('button', { name: 'اعتماد', exact: true }).click();
    await expect.poll(async () => (await api.get('/payroll/runs/' + s.run.id)).status).toBe('approved');
  } finally {
    await api.payrollLive(true);
  }
});

test('an objection from the driver\'s phone is answered in the panel', async ({ admin, api }) => {
  const s = await setup(api);
  await api.payrollLive();
  await api.post(`/payroll/runs/${s.run.id}/approve`);
  const salem = await api.driverPhone(s.driver.id, 'e2e-' + s.n + '-salem');
  const slip = (await salem.call('GET', '/driver/payslips'))[0];
  expect(slip.run_id).toBe(s.run.id);
  const photo = await salem.photo('upload');
  const sent = await salem.call('POST', `/driver/payslips/${s.run.id}/objections`, {
    item_code: 'missing_target', reason: 'عملت 425 طلب حسب تطبيق المنصة ' + s.n, attachment_sha256: photo, client_ref: require('crypto').randomUUID(),
  });
  expect([sent.status, sent.item_amount]).toEqual(['open', '-7.000']);

  await admin.goto('/admin.html#/payroll?tab=objections');
  await settled(admin);
  const row = admin.locator('[data-p=objections] tbody tr', { hasText: s.driver.name.ar });
  await expect(row).toContainText('خصم نقص التارجت');
  await row.click();
  const d = top(admin);
  await expect(d).toContainText('عملت 425 طلب حسب تطبيق المنصة');
  await expect(d.locator('[data-attachment]')).toBeVisible();
  await expect(d).toContainText('الصافي');
  await d.locator('[name=status]').selectOption('accepted');
  await d.locator('[name=response]').fill('صحيح: تُضاف 7.000 مع الشهر القادم');
  await d.locator('[name=action_taken]').fill('بونص 7.000 على كشف الشهر القادم');
  await d.getByRole('button', { name: 'حفظ الرد' }).click();
  await expect(d).toBeHidden();
  const mine = (await salem.call('GET', '/driver/objections'))[0];
  expect([mine.status, mine.response, mine.action_taken]).toEqual(['accepted', 'صحيح: تُضاف 7.000 مع الشهر القادم', 'بونص 7.000 على كشف الشهر القادم']);
  const told = await salem.call('GET', '/driver/notifications');
  expect(told.items[0].kind).toBe('objection_updated');
  expect((await api.get('/payroll/runs/' + s.run.id)).lines[0].net).toBe('123.000'); // the approved run as approved
});

test('a scheme\'s terms change as a new version from a later month', async ({ admin, api }) => {
  const s = await setup(api);
  await admin.goto('/admin.html#/payroll?tab=schemes');
  await settled(admin);
  await admin.locator(`[data-scheme="${s.scheme.id}"]`).click();
  const m = top(admin);
  await expect(m.locator('[name=effective_month]')).toHaveValue(MONTH); // the earliest month offered
  await expect(m.locator('[name=calculator]')).toBeDisabled(); // used: its way of computing stays
  await expect(m.locator('[data-versions] tbody tr')).toHaveCount(1);
  await m.locator('[name=effective_month]').fill(nextMonth());
  await m.locator('[name=per_order]').fill('0.400');
  await m.locator('[name=version_note]').fill('سعر جديد من المنصة');
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  const after = (await api.get('/payroll/schemes')).find((x) => x.id === s.scheme.id);
  expect([after.per_order, after.version_no, after.next_version]).toEqual(['0.350', 1, { version_no: 2, effective_month: nextMonth() + '-01' }]);
  expect(after.versions.map((v) => [v.version_no, v.per_order, v.note])).toEqual([[2, '0.400', 'سعر جديد من المنصة'], [1, '0.350', null]]);
  await expect(admin.locator(`[data-scheme="${s.scheme.id}"] [data-next-version]`)).toContainText('النسخة 2');
  // this month's draft keeps this month's terms
  const run = await api.post(`/payroll/runs/${s.run.id}/recompute`);
  expect(run.lines[0].cells.orders_pay).toBe('140.000');
});
