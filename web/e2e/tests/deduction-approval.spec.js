// A manual deduction under its approval workflow (BRD FR-WFL-02): entered from the deductions page it says it was sent
// for approval and waits under «بانتظار الاعتماد», the approver's decision from the inbox makes it live, and a refused
// one shows its reason. The workflow covers 500 and above only, and is switched off at the end.
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');

async function option(field, text) {
  let found;
  await expect.poll(async () => {
    found = await field.evaluate((el, t) => [...document.getElementById(el.getAttribute('list')).options].map((o) => o.value).find((v) => v.includes(t)), text);
    return found;
  }).toBeTruthy();
  return found;
}

test('a manual deduction sent for approval, approved from the inbox, another refused', async ({ admin, api, playwright, baseURL }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الخصم ' + n, en: 'Deduction company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'K' + uid(), name: { ar: 'سائق الخصم ' + n, en: 'Deduction driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const role = await api.post('/roles', { code: 'ded' + n, name: { ar: 'معتمد الخصومات ' + n, en: 'Deductions approver ' + n }, permissions: ['approvals.view', 'deductions.view'] });
  const password = 'approver-password-' + n;
  await api.post('/users', { username: 'ded' + n, full_name: 'معتمد ' + n, password, role_codes: [role.code], all_companies: true });
  const approver = await playwright.request.newContext({ baseURL });
  const signed = await (await approver.post('/api/v1/auth/login', { data: { username: 'ded' + n, password } })).json();
  const as = (method, path, data) => approver.fetch('/api/v1' + path, { method, data, headers: { 'X-CSRF-Token': signed.csrf_token } }).then((r) => r.json());
  const flow = async () => (await api.get('/approvals/workflows')).find((w) => w.process === 'manual_deduction');
  await api.put('/approvals/workflows/manual_deduction', {
    version: (await flow()).version, active: true, steps: [{ name: { ar: 'اعتماد الخصم', en: 'Deduction approval' }, role: role.code, min_amount: '500' }],
  });
  const top = () => admin.locator('.overlay[data-open]').last();
  try {
    const enter = async (total, reason) => {
      await admin.locator('#ded-new').click();
      const m = top();
      await m.locator('[name=employee]').fill(await option(m.locator('[name=employee]'), driver.employee_number));
      await m.locator('[name=reason]').fill(reason);
      await m.locator('[name=total]').fill(total);
      await clearToasts(admin);
      await m.locator('button[type=submit]').click();
    };
    await admin.goto('/admin.html#/deductions?chip=pending');
    await settled(admin);
    await enter('777', 'سلفة كبيرة ' + n);
    await expect(admin.locator('.toast').last()).toContainText('أُرسل الخصم للاعتماد');
    const row = admin.locator('#view tbody tr', { hasText: 'سلفة كبيرة ' + n });
    await expect(row).toContainText('بانتظار الاعتماد');

    await enter('50', 'سلفة صغيرة ' + n); // under 500: no step, live at once
    await expect(admin.locator('.toast').last()).toContainText('سُجّل الخصم');

    // the approver decides from the inbox: the large one approved, a third one refused
    const waiting = async (part) => (await as('GET', '/approvals/inbox')).find((x) => x.process === 'manual_deduction' && x.document_ref.includes(part));
    expect((await waiting('777.000')).document_ref).toContain(driver.name.ar);
    expect((await as('POST', `/approvals/requests/${(await waiting('777.000')).id}/decide`, { approve: true })).status).toBe('approved');
    await enter('600', 'شريحة ' + n);
    await expect(admin.locator('.toast').last()).toContainText('أُرسل الخصم للاعتماد');
    await as('POST', `/approvals/requests/${(await waiting('600.000')).id}/decide`, { approve: false, reason: 'مدفوعة من قبل' });

    await admin.goto('/admin.html#/deductions?chip=approved');
    await admin.reload();
    await settled(admin);
    await expect(admin.locator('#view tbody tr', { hasText: 'سلفة كبيرة ' + n })).toContainText('معتمد');
    await admin.goto('/admin.html#/deductions?chip=rejected');
    await admin.reload();
    await settled(admin);
    const refused = admin.locator('#view tbody tr', { hasText: 'شريحة ' + n });
    await expect(refused).toContainText('مرفوض');
    await refused.click();
    await expect(top()).toContainText('مدفوعة من قبل');
  } finally {
    await api.put('/approvals/workflows/manual_deduction', { version: (await flow()).version, active: false, steps: [] });
    await approver.dispose();
  }
});
