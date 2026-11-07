// Changing a daily report (BRD FR-DWR-04, FR-DWR-06, BR-06): the reviewer sends it back with the reason, the driver
// corrects it and the drawer shows every change; after approval the driver asks for a change, one is refused with
// its reason and another approved from the list of requests.
const { test, expect, uid, phone, settled } = require('./fixtures');

const kuwaitDay = () => new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 10);

test('a report sent back and corrected, then changes asked for after approval and decided', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة التعديل ' + n, en: 'Changes company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'C' + n, name: { ar: 'سائق التعديل ' + n, en: 'Changes driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const report = await app.call('POST', '/driver/reports', { business_date: kuwaitDay(), orders_count: 9, cash_amount: '15.000', screenshot_sha256: await app.photo() });
  const top = () => admin.locator('.overlay[data-open]').last();
  const open = async (status) => {
    await admin.goto('/admin.html#/daily?status=' + status + '&date=' + kuwaitDay());
    await admin.reload(); // the same address twice: the page must read the server again
    await settled(admin);
    const row = admin.locator('#view tbody tr', { hasText: driver.name.ar });
    await expect(row).toHaveCount(1);
    return row;
  };

  // ---- the reviewer sends it back: the reason is required
  await (await open('submitted')).click();
  await top().getByRole('button', { name: 'إعادة للسائق' }).click();
  await expect(top()).toBeVisible();
  await top().locator('[name=reason]').fill('اللقطة لا تظهر الكاش');
  await top().getByRole('button', { name: 'إعادة للسائق' }).click();
  await expect(top()).toBeHidden();
  await expect(await open('returned')).toContainText('أُعيد للتصحيح');

  // ---- the driver corrects it: back to review, the drawer shows both changes
  await app.call('PATCH', '/driver/reports/' + report.id, { cash_amount: '16.000' });
  await (await open('submitted')).click();
  const log = top().locator('[data-changes]');
  await expect(log.locator('[data-change]')).toHaveCount(2);
  await expect(log.locator('[data-change=returned]')).toContainText('اللقطة لا تظهر الكاش');
  await expect(log.locator('[data-change=edit]')).toContainText('15.000');
  await expect(log.locator('[data-change=edit]')).toContainText('16.000');
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(top()).toBeHidden();

  // ---- after approval: a change refused with its reason, another approved
  const ask = (body) => app.call('POST', `/driver/reports/${report.id}/change-request`, body);
  await ask({ orders_count: 11, reason: 'طلبان متأخران' });
  await open('approved');
  const box = admin.locator('[data-change-requests] [data-change-id]', { hasText: driver.name.ar });
  await expect(box).toContainText('طلبان متأخران');
  await box.getByRole('button', { name: 'رفض' }).click();
  const confirm = top();
  await confirm.locator('[name=reason]').fill('الطلبان في يوم آخر');
  await confirm.getByRole('button', { name: 'رفض' }).click();
  await expect(box).toBeHidden();

  await ask({ cash_amount: '17.500', reason: 'إيصال كاش إضافي' });
  await open('approved');
  await expect(admin.locator('#view tbody tr', { hasText: driver.name.ar })).toContainText('طلب تعديل');
  await box.getByRole('button', { name: 'موافقة' }).click();
  await top().getByRole('button', { name: 'موافقة' }).click();
  await expect(box).toBeHidden();
  const mine = (await app.call('GET', '/driver/reports')).find((r) => r.id === report.id);
  expect([mine.status, mine.approved_cash, mine.orders_count, mine.change_pending]).toEqual(['approved', '17.500', 9, false]);
  const cash = await app.call('GET', '/driver/cash');
  expect(cash.posted).toBe('17.500');
  const changes = await api.get(`/daily-reports/${report.id}/changes`);
  expect(changes.map((c) => [c.kind, c.status])).toEqual([['returned', 'applied'], ['edit', 'applied'], ['request', 'rejected'], ['request', 'approved']]);
});
