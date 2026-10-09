// Petty cash custody: an employee's custody funded from a branch treasury from the panel, then an expense entered
// «من عهدة موظف» that, approved, lowers his custody (and not the treasury); his custody's movements.
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');

test('a custody funded from the treasury, then an expense paid from it', async ({ admin, api }) => {
  test.setTimeout(120_000);
  const n = uid();
  const branch = await api.post('/branches', { name: { ar: 'فرع العهدة ' + n, en: 'Petty branch ' + n } });
  const company = await api.post('/companies', { name: { ar: 'شركة العهدة ' + n, en: 'Petty company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'P' + uid(), name: { ar: 'سائق العهدة ' + n, en: 'Petty driver ' + n },
    company_id: company.id, branch_id: branch.id, is_driver: true, phone: phone(),
  });
  const holder = await api.post('/employees', {
    employee_number: 'H' + uid(), name: { ar: 'موظف العهدة ' + n, en: 'Petty holder ' + n },
    company_id: company.id, branch_id: branch.id, is_driver: false,
  });
  await api.post('/cash/receipts', { driver_id: driver.id, amount: '50' }); // the branch treasury: 50
  const top = () => admin.locator('.overlay[data-open]').last();
  const row = () => admin.locator('#petty-panel tr[data-holder="' + holder.id + '"]');

  // ---- funded from the panel: 20 out of the branch treasury
  await admin.goto('/admin.html#/cash?tab=petty');
  await settled(admin);
  await admin.locator('#petty-panel [data-petty-fund]').click();
  const m = top();
  await m.locator('[name=holder]').fill(holder.employee_number + ' · موظف العهدة ' + n);
  await m.locator('[name=branch_id]').selectOption(String(branch.id));
  await m.locator('[name=amount]').fill('20');
  await m.locator('[name=note]').fill('مصروفات المكتب');
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('تم صرف العهدة');
  await expect(row().locator('td').nth(2)).toHaveText('20.000');

  // ---- an expense paid from his custody, entered from the expense form
  await admin.goto('/admin.html#/finance?tab=expenses');
  await settled(admin);
  await admin.locator('[data-action=expense-new]').first().click();
  const e = top();
  await e.locator('[name=company]').selectOption(String(company.id));
  await e.locator('[name=amount]').fill('7.250');
  await e.locator('[name=method]').selectOption('petty');
  await e.locator('[name=petty_holder]').selectOption(holder.id);
  await e.locator('[name=supplier]').fill('مكتبة ' + n);
  await clearToasts(admin);
  await e.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('سُجّل المصروف');
  const [expense] = (await api.get('/finance/expenses?status=pending&limit=50')).filter((x) => x.supplier === 'مكتبة ' + n);
  expect([expense.payment_method, expense.petty_employee.id]).toEqual(['petty', holder.id]);
  await api.post(`/finance/expenses/${expense.id}/approve`, {});

  // approved: out of his custody, not out of the treasury
  await admin.goto('/admin.html#/cash?tab=petty');
  await settled(admin);
  await expect(row().locator('td').nth(2)).toHaveText('12.750');
  await row().locator('[data-petty-moves]').click();
  const lines = top().locator('[data-mv-lines] tbody tr[data-line]');
  await expect(lines).toHaveCount(2);
  await expect(lines.nth(1)).toContainText('EXP-' + expense.number);
  await expect(lines.nth(1).locator('td').nth(4)).toHaveText('12.750');
  await admin.keyboard.press('Escape');
  const boxes = await api.get('/cash/treasury');
  expect(boxes.find((b) => b.branch.id === branch.id).treasury).toBe('30.000');
});
