// The treasury on screen is the books: an expense paid from a branch's treasury lowers the treasury shown in «الخزينة
// والبنك» and appears in the branch's movements with its running balance; cash taken from the bank back to the
// treasury with the photo of the slip, then reversed from the movements; and a GL reversal dated by the accountant.
const { test, expect, uid, phone, settled, clearToasts, jpeg, pdf } = require('./fixtures');

const kuwaitDay = (offset = 0) => new Date(Date.now() + 3 * 3600e3 + offset * 86400e3).toISOString().slice(0, 10);

test('a treasury expense lowers the branch treasury and shows in its movements; a withdrawal from the bank', async ({ admin, api }) => {
  test.setTimeout(120_000);
  const n = uid();
  // a branch of its own: its balances are this test's alone
  const branch = await api.post('/branches', { name: { ar: 'فرع الخزينة ' + n, en: 'Treasury branch ' + n } });
  const company = await api.post('/companies', { name: { ar: 'شركة الخزينة ' + n, en: 'Treasury company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'T' + uid(), name: { ar: 'سائق الخزينة ' + n, en: 'Treasury driver ' + n },
    company_id: company.id, branch_id: branch.id, is_driver: true, phone: phone(),
  });
  await api.post('/cash/receipts', { driver_id: driver.id, amount: '50' }); // the treasury: 50
  const photo = await api.upload('dep.pdf', 'application/pdf', pdf()); // the bank's receipt as a PDF
  await api.post('/cash/bank-deposits', { branch_id: branch.id, amount: '20', reference: 'DEP-' + n, receipt_sha256: photo }); // 30 / bank 20
  const fuel = (await api.get('/finance/expense-types')).find((t) => t.code === 'fuel');
  const e = await api.post('/finance/expenses', {
    company_id: company.id, branch_id: branch.id, type_id: fuel.id, expense_date: kuwaitDay(), amount: '7', payment_method: 'treasury',
  });
  const row = () => admin.locator('#tre-panel tr[data-branch="' + branch.public_id + '"]');
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/cash?tab=treasury');
  await settled(admin);
  await expect(row()).toContainText('30.000'); // still pending: nothing out yet
  await api.post(`/finance/expenses/${e.id}/approve`, {});
  await admin.reload();
  await settled(admin);
  await expect(row().locator('td').nth(1)).toHaveText('23.000'); // approved: out of the treasury
  await expect(row().locator('td').nth(2)).toHaveText('20.000');

  // its movements: the receipt, the deposit, the expense, each with the balance after it
  await row().locator('[data-moves]').click();
  const lines = top().locator('[data-mv-lines] tbody tr[data-line]');
  await expect(lines).toHaveCount(3);
  await expect(lines.nth(0)).toContainText('سائق الخزينة ' + n);
  await expect(lines.nth(0)).toContainText('50.000');
  await expect(lines.nth(1)).toContainText('DEP-' + n);
  await expect(lines.nth(2)).toContainText('EXP-' + e.number);
  await expect(lines.nth(2).locator('td').nth(4)).toHaveText('23.000');
  await expect(lines.nth(2).locator('[data-rev]')).toHaveCount(0); // undone only by cancelling the expense
  await expect(lines.nth(1).locator('[data-rev]')).toHaveCount(1);
  // a PDF opens in a new tab, not in the image viewer
  const link = lines.nth(1).locator('a[data-att-link]');
  await expect(link).toHaveAttribute('target', '_blank');
  const file = await admin.request.get(await link.getAttribute('href'));
  expect(file.status()).toBe(200);
  expect(file.headers()['content-type']).toContain('application/pdf');
  await admin.keyboard.press('Escape');
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  // ---- 5.000 from the bank to the treasury, with the slip's photo
  await admin.locator('#tre-panel [data-wd]').click();
  const m = top();
  await m.locator('[name=branch_id]').selectOption(String(branch.id));
  await m.locator('[name=amount]').fill('5');
  await m.locator('[name=reference]').fill('WD-' + n);
  await m.locator('[name=photo]').setInputFiles({ name: 'slip.jpg', mimeType: 'image/jpeg', buffer: jpeg() });
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('تم تسجيل السحب');
  await expect(row().locator('td').nth(1)).toHaveText('28.000');
  await expect(row().locator('td').nth(2)).toHaveText('15.000');

  // ---- the bank's movements: the deposit in, the withdrawal out; the withdrawal reversed from here
  await row().click();
  await top().locator('[data-acc=bank]').click();
  const bank = top().locator('[data-mv-lines] tbody tr[data-line]');
  await expect(bank).toHaveCount(2);
  const wd = bank.filter({ hasText: 'WD-' + n });
  await expect(wd).toContainText('5.000');
  await expect(wd.locator('td').nth(4)).toHaveText('15.000');
  await wd.locator('[data-att]').click(); // the slip's photo in the viewer
  await expect(admin.locator('.lightbox-ov[data-open] .lb-stage img')).toHaveCount(1);
  await admin.keyboard.press('Escape');
  await expect(admin.locator('.lightbox-ov[data-open]')).toHaveCount(0);
  await wd.locator('[data-rev]').click();
  await top().locator('[name=reason]').fill('سحب مكرر');
  await clearToasts(admin);
  await top().getByRole('button', { name: 'عكس', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('تم عكس الحركة');
  await expect(bank).toHaveCount(3);
  await expect(bank.nth(2).locator('td').nth(4)).toHaveText('20.000');
  await admin.keyboard.press('Escape');
  await expect(row().locator('td').nth(1)).toHaveText('23.000');
});

test('a GL reversal dated by the accountant', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة العكس ' + n, en: 'Reversal company ' + n } });
  const other = (await api.get('/finance/expense-types')).find((t) => t.code === 'other');
  const day = kuwaitDay(-3), chosen = kuwaitDay(-1);
  const e = await api.post('/finance/expenses', {
    company_id: company.id, type_id: other.id, expense_date: day, amount: '3.250', payment_method: 'bank', supplier: 'مورد ' + n,
  });
  await api.post(`/finance/expenses/${e.id}/approve`, {});
  await api.post('/finance/entries/post', { date_from: day, date_to: kuwaitDay() });
  const entry = (await api.get(`/finance/entries?date_from=${day}&date_to=${day}&q=EXP-${e.number}`))[0];
  await api.post('/finance/entries/approve', { ids: [entry.id] });
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/finance?tab=entries');
  await settled(admin);
  const from = admin.locator('#view [data-panel=entries] [data-from]');
  await from.fill(day);
  await from.dispatchEvent('change');
  await admin.locator('#view [data-panel=entries] [data-chip=approved]').click();
  const approved = admin.locator('#view [data-panel=entries] tbody tr', { hasText: 'EXP-' + e.number });
  await expect(approved).toHaveCount(1);
  await approved.click();
  await top().getByRole('button', { name: 'قيد عكسي' }).click();
  const m = top();
  await expect(m.locator('[name=entry_date]')).toHaveValue(kuwaitDay());
  await m.locator('[name=entry_date]').fill(chosen);
  await m.locator('[name=reason]').fill('مورد خطأ');
  await clearToasts(admin);
  await m.getByRole('button', { name: 'عكس القيد' }).click();
  await expect(admin.locator('.toast').last()).toContainText('أُنشئ القيد العكسي');
  const reversal = (await api.get(`/finance/entries?date_from=${day}&date_to=${kuwaitDay()}&source_kind=reversal&q=EXP-${e.number}`))[0];
  expect(reversal.entry_date).toBe(chosen);
  expect(reversal.reverses).toBe(entry.number);
});
