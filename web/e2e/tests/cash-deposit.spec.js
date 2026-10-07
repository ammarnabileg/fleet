// The treasury's cash taken to the bank with the photo of the bank's receipt (BRD FR-CSH-07): refused without it, then
// kept with the deposit and opened from the cash report; and the receipts a driver has not confirmed after a day
// (FR-CSH-05) listed above the balances.
const { test, expect, uid, phone, settled, clearToasts, jpeg } = require('./fixtures');

test('a bank deposit keeps the photo of its receipt, opened from the cash report', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الإيداع ' + n, en: 'Deposit company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'B' + uid(), name: { ar: 'سائق الإيداع ' + n, en: 'Deposit driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const given = await api.post('/cash/receipts', { driver_id: driver.id, amount: '9' }); // into the branch's treasury
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/cash?tab=treasury');
  await settled(admin);
  await admin.locator('#tre-panel [data-dep]').click();
  const m = top();
  await m.locator('[name=branch_id]').selectOption(String(given.branch_id));
  await m.locator('[name=amount]').fill('3');
  await m.locator('[name=reference]').fill('BANK-' + n);
  const sent = [];
  admin.on('request', (r) => { if (r.url().includes('/cash/bank-deposits')) sent.push(r); });
  await m.locator('button[type=submit]').click();
  await expect(m.locator('[name=photo]').locator('xpath=ancestor::div[contains(@class,"field")]')).toContainText('يلزم إرفاق ملف');
  expect(sent).toHaveLength(0); // no photo, no deposit

  const photo = jpeg();
  await m.locator('[name=photo]').setInputFiles({ name: 'bank.jpg', mimeType: 'image/jpeg', buffer: photo });
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('تم تسجيل الإيداع');

  const today = new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 10);
  const report = await api.get(`/reports/cash?date_from=${today}&date_to=${today}`);
  const [dep] = report.deposits.filter((d) => d.reference === 'BANK-' + n);
  expect([dep.amount, dep.has_receipt]).toEqual(['3.000', true]);

  await admin.goto('/admin.html#/reports?tab=cash');
  await settled(admin);
  const row = admin.locator('[data-p=cash] [data-dep] tbody tr', { hasText: 'BANK-' + n });
  await expect(row).toHaveCount(1);
  const href = await row.locator('[data-receipt]').getAttribute('href');
  const file = await admin.request.get(href);
  expect(file.status()).toBe(200);
  expect(Buffer.from(await file.body()).equals(photo)).toBe(true); // the very photo sent with the deposit
});

test('receipts not confirmed after a day are listed above the balances', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الإيصالات ' + n, en: 'Receipts company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'U' + uid(), name: { ar: 'سائق لم يؤكد ' + n, en: 'Unconfirmed driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const given = await api.post('/cash/receipts', { driver_id: driver.id, amount: '6.250' });
  // a receipt cannot be made a day old from here: the backend tests check the 24 hours; this checks the page shows
  // what the API answers, with the real receipt made to look two days old
  await admin.route('**/api/v1/cash/receipts/unconfirmed', (r) => r.fulfill({
    json: [{ ...given, created_at: new Date(Date.now() - 2 * 86400e3).toISOString(), unconfirmed_late: true, driver: { id: driver.id, name: driver.name } }],
  }));
  await admin.goto('/admin.html#/cash');
  await settled(admin);
  const box = admin.locator('#bal-panel [data-unconfirmed]');
  await expect(box).toContainText('لم يؤكدها السائق');
  const row = box.locator(`tr[data-receipt="${given.id}"]`);
  await expect(row).toContainText(driver.name.ar);
  await expect(row).toContainText(String(given.receipt_no));
  await expect(row).toContainText('6.250');

  await admin.unroute('**/api/v1/cash/receipts/unconfirmed');
  await admin.reload();
  await settled(admin);
  await expect(admin.locator('#bal-panel [data-bal]')).toBeVisible();
  await expect(admin.locator(`#bal-panel tr[data-receipt="${given.id}"]`)).toHaveCount(0); // given just now: not late
});
