// The daily report's evidence (BRD FR-DWR-02, FR-DWR-05): today's report waits for the end-of-day odometer reading,
// and the reviewer sees both odometer photos and the day's distance beside the numbers.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

const kuwaitDay = () => new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 10);

test('the report after a started day needs its end-of-day reading; the reviewer sees the odometer', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة العداد ' + n, en: 'Odometer company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '5/' + n.slice(-6), make: 'Kia', model: 'Pegas', company_id: company.id, last_odometer_km: 12000 });
  const driver = await api.post('/employees', {
    employee_number: 'E' + n, name: { ar: 'سائق العداد ' + n, en: 'Odometer driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 12000, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
  });

  // ---- his phone: the day started, the report refused until the day is closed
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const reading = async (kind, km) => app.call('POST', '/driver/odometer', {
    kind, value_km: km, photo_sha256: await app.photo('camera'), recorded_at: new Date().toISOString(),
  });
  await reading('start_day', 12010);
  expect((await app.call('GET', '/driver/reports/form')).end_reading).toBe(true);
  const report = async () => app.call('POST', '/driver/reports', { business_date: kuwaitDay(), orders_count: 14, cash_amount: '9.250', screenshot_sha256: await app.photo() });
  await expect(report()).rejects.toThrow(/end_reading_required/);
  await reading('end_day', 12095);
  expect((await app.call('GET', '/driver/today')).end_day_done).toBe(true);
  await report();

  // ---- the reviewer: both photos, the distance, no history yet
  await admin.goto('/admin.html#/daily?date=' + kuwaitDay());
  await settled(admin);
  await admin.locator('#view tbody tr', { hasText: driver.name.ar }).click();
  const drawer = admin.locator('.overlay[data-open]').last();
  const ev = drawer.locator('[data-evidence]');
  await expect(ev).toContainText('عداد بداية اليوم 12,010 كم');
  await expect(ev).toContainText('عداد نهاية اليوم 12,095 كم');
  await expect(ev).toContainText('مسافة اليوم85 كم');
  await expect(ev).toContainText('لا توجد تقارير معتمدة في آخر 30 يوماً');
  await expect(ev.locator('img')).toHaveCount(2);
  await drawer.getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(drawer).toBeHidden();

  // ---- he works again the same day: a second session, its own report, the day's distance adds up
  await reading('start_day', 12100);
  expect(await app.call('GET', '/driver/today')).toMatchObject({ start_day_done: true, end_day_done: false, sessions: 2 });
  await reading('end_day', 12150);
  const second = await app.call('POST', '/driver/reports', { business_date: kuwaitDay(), orders_count: 4, cash_amount: '2.000', screenshot_sha256: await app.photo() });
  expect(second.session).toBe(2);
  await admin.reload();
  await settled(admin);
  const row = admin.locator('#view tbody tr', { hasText: driver.name.ar }).filter({ hasText: 'فترة 2' });
  await expect(row).toHaveCount(1);
  await row.click();
  const ev2 = admin.locator('.overlay[data-open]').last().locator('[data-evidence]');
  await expect(ev2).toContainText('عداد بداية اليوم 12,010 كم');
  await expect(ev2).toContainText('عداد نهاية اليوم 12,150 كم');
  await expect(ev2).toContainText('مسافة اليوم135 كم');
});
