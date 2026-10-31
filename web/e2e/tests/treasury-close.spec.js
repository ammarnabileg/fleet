// The treasury's daily count and close: the cash in the drawer counted by notes and coins against the books, a
// shortage explained and posted, the treasury on screen then equal to the count, the closed day listed, and a
// movement on the closed day refused with its reason.
const { test, expect, uid, phone, settled, clearToasts, jpeg } = require('./fixtures');

test('a day closed with a shortage; a movement on it is refused after', async ({ admin, api }) => {
  test.setTimeout(120_000);
  const n = uid();
  // a branch of its own: closing its day touches no other test
  const branch = await api.post('/branches', { name: { ar: 'فرع الجرد ' + n, en: 'Count branch ' + n } });
  const company = await api.post('/companies', { name: { ar: 'شركة الجرد ' + n, en: 'Count company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'C' + uid(), name: { ar: 'سائق الجرد ' + n, en: 'Count driver ' + n },
    company_id: company.id, branch_id: branch.id, is_driver: true, phone: phone(),
  });
  await api.post('/cash/receipts', { driver_id: driver.id, amount: '50' }); // the treasury: 50
  const row = () => admin.locator('#tre-panel tr[data-branch="' + branch.public_id + '"]');
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/cash?tab=treasury');
  await settled(admin);
  await expect(row().locator('td').nth(1)).toHaveText('50.000');
  await row().locator('[data-close-day]').click();
  const m = top();
  await expect(m.locator('[data-book]')).toHaveText('50.000');
  // counted by notes: 2 x 20 + 1 x 5 = 45, the difference shown as a shortage
  await m.locator('[data-denoms-box] summary').click();
  await m.locator('[data-den="20"]').fill('2');
  await m.locator('[data-den="5"]').fill('1');
  await expect(m.locator('[name=counted]')).toHaveValue('45.000');
  await expect(m.locator('[data-diff]')).toContainText('5.000');
  await expect(m.locator('[data-diff]')).toHaveClass(/t-danger/);
  // a difference needs its reason
  await clearToasts(admin);
  await m.getByRole('button', { name: 'إقفال اليوم' }).click();
  await expect(admin.locator('.toast').last()).toContainText('اكتب سبب الفرق');
  await m.locator('[name=note]').fill('عجز 5 د.ك، الكاشير يوضح');
  await clearToasts(admin);
  await m.getByRole('button', { name: 'إقفال اليوم' }).click();
  await expect(admin.locator('.toast').last()).toContainText('تم إقفال اليوم');
  await expect(row().locator('td').nth(1)).toHaveText('45.000'); // the screen is the count
  const closing = admin.locator('#tre-panel [data-closings-table] tbody tr', { hasText: 'فرع الجرد ' + n });
  await expect(closing).toHaveCount(1);
  await expect(closing).toContainText('5.000');
  await expect(closing).toContainText('الكاشير يوضح');
  await expect(closing.locator('[data-reopen]')).toHaveCount(1);

  // the movements say the day is closed
  await row().locator('[data-moves]').click();
  await expect(top().locator('[data-closed-through]')).toBeVisible();
  await expect(top().locator('[data-mv-lines] tbody tr[data-line]')).toHaveCount(2);
  await admin.keyboard.press('Escape');
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  // a bank deposit today on the closed day: refused, with the reason on screen
  admin.allow(/HTTP 409 POST .*\/cash\/bank-deposits/);
  await admin.locator('#tre-panel [data-dep]').click();
  const d = top();
  await d.locator('[name=branch_id]').selectOption(String(branch.id));
  await d.locator('[name=amount]').fill('10');
  await d.locator('[name=reference]').fill('DEP-' + n);
  await d.locator('[name=photo]').setInputFiles({ name: 'dep.jpg', mimeType: 'image/jpeg', buffer: jpeg() });
  await clearToasts(admin);
  await d.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('مقفول بالجرد');
  await admin.keyboard.press('Escape');
  // and a driver's cash handed in at the cashier
  await expect(api.post('/cash/receipts', { driver_id: driver.id, amount: '1' })).rejects.toThrow(/409.*treasury_day_closed/);
  await admin.reload();
  await settled(admin);
  await expect(row().locator('td').nth(1)).toHaveText('45.000');
});
