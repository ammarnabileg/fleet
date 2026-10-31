// Petty cash spending from the driver app: the holder records what he spent from his custody with the invoice's
// camera photo; the office approves it in the cash page's petty tab (his custody goes down through a finance expense
// paid from it) or rejects it with a reason (nothing moves, he is told why).
const { test, expect, uid, phone, settled } = require('./fixtures');

async function holderWithCustody(api, n, amount) {
  const branch = await api.post('/branches', { name: { ar: 'فرع مصروف العهدة ' + n, en: 'Spending branch ' + n } });
  const company = await api.post('/companies', { name: { ar: 'شركة مصروف العهدة ' + n, en: 'Spending company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'S' + uid(), name: { ar: 'سائق مصروف العهدة ' + n, en: 'Spending driver ' + n },
    company_id: company.id, branch_id: branch.id, is_driver: true, phone: phone(),
  });
  await api.post('/cash/receipts', { driver_id: driver.id, amount: '50' }); // the branch treasury: 50
  await api.post(`/cash/petty/${driver.id}/fund`, { branch_id: branch.id, amount });
  return { branch, company, driver };
}

const spend = async (app, types, amount, extra = {}) => app.call('POST', '/driver/petty/expenses', {
  client_ref: require('crypto').randomUUID(), amount, category: types.find((t) => t.code === 'office').id,
  invoice_sha256: await app.photo('camera'), ...extra,
});

test('spent from the custody in the app, approved in the panel: the custody goes down', async ({ admin, api }) => {
  test.setTimeout(120_000);
  const n = uid();
  const { driver } = await holderWithCustody(api, n, '20');
  const app = await api.driverPhone(driver.id, 'e2e-petty-' + n);
  const view = await app.call('GET', '/driver/petty');
  expect([view.has_custody, view.balance, view.available]).toEqual([true, '20.000', '20.000']);
  const mine = await spend(app, view.categories, '6.750', { vendor: 'مكتبة ' + n, note: 'ورق طباعة' });
  expect(mine.status).toBe('pending');
  expect((await app.call('GET', '/driver/petty')).available).toBe('13.250');

  await admin.goto('/admin.html#/cash?tab=petty');
  await settled(admin);
  const holderRow = admin.locator('#petty-panel tr[data-holder="' + driver.id + '"]');
  await expect(holderRow.locator('[data-holder-pending]')).toContainText('6.750');
  const row = admin.locator('#petty-panel [data-petty-pending-id="' + mine.id + '"]');
  await expect(row).toContainText('6.750');
  await expect(row).toContainText('مكتبة ' + n);
  await expect(row.locator('.thumbs img')).toHaveCount(1);
  await row.getByRole('button', { name: 'اعتماد' }).click();
  const m = admin.locator('.overlay[data-open]').last();
  await m.getByRole('button', { name: 'اعتماد' }).click();
  await expect(m).toBeHidden();
  await expect(row).toHaveCount(0);
  await expect(holderRow.locator('td').nth(2)).toHaveText('13.250');
  await expect(holderRow.locator('[data-holder-pending]')).toHaveText('—');

  const after = await app.call('GET', '/driver/petty');
  expect([after.balance, after.expenses[0].status]).toEqual(['13.250', 'approved']);
  const [expense] = (await api.get('/finance/expenses?limit=100')).filter((x) => x.supplier === 'مكتبة ' + n);
  expect([expense.status, expense.payment_method, expense.petty_employee.id]).toEqual(['approved', 'petty', driver.id]);
});

test('spent from the custody in the app, rejected in the panel with a reason: nothing moves', async ({ admin, api }) => {
  test.setTimeout(120_000);
  const n = uid();
  const { driver } = await holderWithCustody(api, n, '10');
  const app = await api.driverPhone(driver.id, 'e2e-petty-r-' + n);
  const view = await app.call('GET', '/driver/petty');
  const mine = await spend(app, view.categories, '3.500', { vendor: 'محل ' + n });

  await admin.goto('/admin.html#/cash?tab=petty');
  await settled(admin);
  const row = admin.locator('#petty-panel [data-petty-pending-id="' + mine.id + '"]');
  await row.getByRole('button', { name: 'رفض' }).click();
  const m = admin.locator('.overlay[data-open]').last();
  await m.locator('textarea, input[type=text]').first().fill('الفاتورة غير واضحة');
  await m.getByRole('button', { name: 'رفض' }).click();
  await expect(m).toBeHidden();
  await expect(row).toHaveCount(0);
  const listed = admin.locator('#petty-panel [data-petty-spending-table] tbody tr', { hasText: 'محل ' + n });
  await expect(listed).toContainText('مرفوض');
  await expect(listed).toContainText('الفاتورة غير واضحة');

  const after = await app.call('GET', '/driver/petty');
  expect([after.balance, after.expenses[0].status, after.expenses[0].decision_note]).toEqual(['10.000', 'rejected', 'الفاتورة غير واضحة']);
});
