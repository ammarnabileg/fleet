// Work violations from the panel (BRD FR-VIO-01..05, BR-09/10/13, UAT-05): one recorded for a late order, approved
// with a penalty; the driver objects from the app and the objection is decided finally (the penalty becomes a
// deduction); an order the customer cancelled is excluded as it is recorded; a speeding alert turned into a violation.
const { test, expect, uid, phone, settled, clearToasts, jpeg } = require('./fixtures');

async function option(field, text) {
  let found;
  await expect.poll(async () => {
    found = await field.evaluate((el, t) => [...document.getElementById(el.getAttribute('list')).options].map((o) => o.value).find((v) => v.includes(t)), text);
    return found;
  }).toBeTruthy();
  return found;
}

test('recorded, approved, objected to from the app and decided; excluded for the customer; from a speeding alert', async ({ admin, api }) => {
  test.setTimeout(150_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المخالفات ' + n, en: 'Violations company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '5/' + n.slice(-6), company_id: company.id, last_odometer_km: 1000 });
  const driver = await api.post('/employees', {
    employee_number: 'V' + uid(), name: { ar: 'سائق المخالفات ' + n, en: 'Violations driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 1000, photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 3 * 3600e3).toISOString(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-v' + n);
  const top = () => admin.locator('.overlay[data-open]').last();
  const toast = () => admin.locator('.toast').last();
  const list = () => admin.locator('#violations-list');

  async function recordFromPanel(type, reference, cause) {
    await admin.locator('#view [data-action=violation-new]').click();
    const m = top();
    await m.locator('[name=drv]').fill(await option(m.locator('[name=drv]'), driver.name.ar));
    await m.locator('[name=type]').selectOption({ label: type });
    await m.locator('[name=reference]').fill(reference);
    if (cause) await m.locator('[name=cause]').selectOption({ label: cause });
    await m.locator('[name=description]').fill('الطلب ' + reference);
    await clearToasts(admin);
    await m.locator('button[type=submit]').click();
  }

  await admin.goto('/admin.html#/violations');
  await settled(admin);
  // ---- UAT-05: the customer cancelled: excluded as it is recorded, never reviewed
  await recordFromPanel('الطلبات — رفض طلب', 'C-' + n, 'إلغاء من العميل');
  await expect(toast()).toContainText('سُجّلت واستُبعدت');
  await expect(list().locator('tbody tr', { hasText: 'C-' + n })).toHaveCount(0); // not in the review list

  // ---- a late order: reviewed and approved with a penalty
  await recordFromPanel('الطلبات — تأخر توصيل طلب', 'L-' + n);
  await expect(toast()).toContainText('تنتظر المراجعة');
  const row = list().locator('tbody tr', { hasText: 'L-' + n });
  await row.click();
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await top().locator('[name=amount]').fill('5');
  await clearToasts(admin);
  await top().locator('button[type=submit]').click();
  await expect(toast()).toContainText('اعتُمدت المخالفة');
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0); // the drawer closes with the decision
  await expect(row).toHaveCount(0);

  // ---- the driver objects from the app; the objection is rejected finally and the penalty deducted
  const [mine] = (await app.call('GET', '/driver/violations')).filter((v) => v.reference === 'L-' + n);
  expect([mine.status, mine.can_object, mine.amount]).toEqual(['approved', true, '5.000']);
  await app.call('POST', '/driver/violations/' + mine.id + '/objection', { text: 'المطعم أخّر الطلب', file_sha256: await app.photo('upload') });
  await list().locator('[data-chip=objections]').click();
  const objected = list().locator('tbody tr', { hasText: 'L-' + n });
  await objected.click();
  await expect(top().locator('[data-objection]')).toContainText('المطعم أخّر الطلب');
  await expect(top().locator('img')).toHaveCount(1); // the screenshot he attached
  await top().getByRole('button', { name: 'رفض الاعتراض' }).click();
  await top().locator('[name=reason]').fill('سجل المطعم يقول التسليم في وقته');
  await clearToasts(admin);
  await top().getByRole('button', { name: 'رفض الاعتراض' }).last().click();
  await expect(toast()).toContainText('رُفض الاعتراض');
  const final = await api.get('/violations/' + mine.id);
  expect([final.status, final.final, final.deduction.total, final.deduction.source_type]).toEqual(['upheld', true, '5.000', 'violation']);

  // ---- BR-13: speeding from the phone is an alert until a supervisor turns it into a violation
  const at = new Date(Date.now() - 60e3).toISOString();
  await app.call('POST', '/driver/positions', { sent_at: new Date().toISOString(), points: [{ seq: 1, recorded_at: at, lat: 29.37, lng: 47.97, speed_kmh: 155 }] });
  await admin.goto('/admin.html#/alerts');
  await settled(admin);
  const alertRow = admin.locator('#alerts-table tbody tr', { hasText: driver.name.ar }).filter({ hasText: '155' });
  await alertRow.locator('[data-violation]').click();
  const m = top();
  await expect(m.locator('[name=drv]')).toHaveValue(new RegExp(driver.name.ar));
  await expect(m.locator('[name=type] option:checked')).toHaveText('التتبع — تجاوز السرعة');
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(toast()).toContainText('تنتظر المراجعة');
  await expect(alertRow).toHaveCount(0); // handled by becoming a violation
  await expect(admin.locator('#alerts-table tbody tr', { hasText: driver.name.ar })).toContainText('بانتظار المراجعة'); // the violation's
  const rows = await api.get('/violations?status=pending&driver_id=' + driver.id);
  expect(rows.map((x) => [x.type.code, x.origin])).toEqual([['speeding', 'alert']]);
});
