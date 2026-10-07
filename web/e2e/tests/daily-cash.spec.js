// A driver's day from his phone to the treasury: the daily report with its cash and screenshot, corrected and approved
// by the reviewer (another refused with a reason), the cash balance it makes, and a receipt the driver confirms.
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');

const day = (back) => new Date(Date.now() + 3 * 3600e3 - back * 86400e3).toISOString().slice(0, 10); // Kuwait date

test('daily report: corrected and approved, another refused, then the cash collected by receipt', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة اليوميات ' + n, en: 'Daily company ' + n } });
  const platform = await api.post('/payroll/platforms', { code: 'p' + n, name: { ar: 'منصة ' + n, en: 'Platform ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'D' + uid(), name: { ar: 'سائق اليوميات ' + n, en: 'Daily driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(), platform_id: platform.id,
  });
  const top = () => admin.locator('.overlay[data-open]').last();
  const name = driver.name.ar;

  // ---- his phone: what his platform asks, then today's report and yesterday's
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const form = await app.call('GET', '/driver/reports/form');
  expect(form.fields).toEqual(['orders', 'cash']);
  await app.call('POST', '/driver/reports', { business_date: day(0), orders_count: 23, cash_amount: '18.500', screenshot_sha256: await app.photo() });
  await app.call('POST', '/driver/reports', { business_date: day(1), orders_count: 9, cash_amount: '40.000', screenshot_sha256: await app.photo() });
  expect((await api.get(`/cash/drivers/${driver.id}/statement`)).pending).toBe('58.500'); // waiting for review

  // ---- the reviewer, on the day's page: today's corrected to 17.250 with the reason
  const reports = async (back) => {
    await admin.goto('/admin.html#/daily?date=' + day(back));
    await settled(admin);
    await expect(admin.locator('#view [data-day]')).toHaveValue(day(back));
    return admin.locator('#view tbody tr', { hasText: name });
  };
  let rows = await reports(0);
  await expect(rows).toHaveCount(1);
  await expect(rows).toContainText('18.500');
  await rows.click();
  const r1 = top();
  await expect(r1).toContainText('23');
  await r1.locator('[name=cash_amount]').fill('17.250');
  await r1.locator('[name=reason]').fill('اللقطة تقول 17.250');
  await r1.getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(r1).toBeHidden();

  await expect(rows).toHaveCount(0); // no longer waiting for review

  // ---- yesterday's refused: a reason is required
  rows = await reports(1);
  await expect(rows).toContainText('40.000');
  await rows.click();
  const r2 = top();
  await r2.getByRole('button', { name: 'رفض', exact: true }).click();
  await expect(r2).toBeVisible(); // no reason: still open
  await r2.locator('[name=reason]').fill('اللقطة لا تخص هذا اليوم');
  await r2.getByRole('button', { name: 'رفض', exact: true }).click();
  await expect(r2).toBeHidden();

  const mine = (await app.call('GET', '/driver/reports')).sort((a, b) => a.business_date.localeCompare(b.business_date));
  expect(mine.map((x) => [x.status, x.approved_cash, x.review_note])).toEqual([
    ['rejected', null, 'اللقطة لا تخص هذا اليوم'],
    ['approved', '17.250', 'اللقطة تقول 17.250'],
  ]);
  let cash = await app.call('GET', '/driver/cash');
  expect([cash.posted, cash.pending, cash.total]).toEqual(['17.250', '0.000', '17.250']);

  // ---- the cash page: 10.000 collected by receipt from his row; he confirms it in the app
  await admin.goto('/admin.html#/cash');
  await settled(admin);
  await search(admin, name);
  const row = admin.locator('#view tbody tr', { hasText: name });
  await expect(row).toContainText('17.250');
  await row.locator('[data-row-menu]').click();
  await admin.getByRole('menuitem', { name: 'استلام كاش بإيصال' }).click();
  await top().locator('[name=amount]').fill('10');
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('إيصال رقم');
  cash = await app.call('GET', '/driver/cash');
  expect(cash.total).toBe('7.250');
  const receipt = cash.receipts.find((x) => x.amount === '10.000');
  expect(receipt.driver_confirmed_at).toBeNull();
  await app.call('POST', `/driver/cash/receipts/${receipt.id}/confirm`);
  cash = await app.call('GET', '/driver/cash');
  expect(cash.receipts.find((x) => x.id === receipt.id).driver_confirmed_at).not.toBeNull();
});
