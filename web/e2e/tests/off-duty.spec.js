// Movement outside the work day (BRD FR-TRK-09): on the route page the stretches before the driver's start of day and
// after his end of day are marked and counted apart; a user without tracking.off_duty sees his work day only, with
// the number of points left out.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

test('the route marks the driver\'s own time, and hides it from who may not see it', async ({ admin, api, browser, baseURL }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المسار ' + n, en: 'Route company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '6/' + n.slice(-6), company_id: company.id, last_odometer_km: 20000 });
  const driver = await api.post('/employees', {
    employee_number: 'R' + uid(), name: { ar: 'سائق المسار ' + n, en: 'Route driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 20000, photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 4 * 3600e3).toISOString(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const ago = (min) => new Date(Date.now() - min * 60e3).toISOString();
  let seq = 0;
  const points = (...list) => app.call('POST', '/driver/positions', {
    sent_at: new Date().toISOString(), points: list.map(([min, lat]) => ({ seq: ++seq, recorded_at: ago(min), lat, lng: 47.98, speed_kmh: 30 })),
  });
  const reading = async (kind, km, min) => app.call('POST', '/driver/odometer', { kind, value_km: km, photo_sha256: await app.photo('camera'), recorded_at: ago(min) });

  await points([200, 29.30], [190, 29.31]); // before his day
  await reading('start_day', 20010, 150);
  await points([120, 29.32], [110, 29.33]); // at work
  await reading('end_day', 20090, 90);
  await points([60, 29.34], [50, 29.35]); // after it
  const url = `/admin.html#/tracking?route=${vehicle.id}`;
  admin.allow(/\/maps\//); // the map extract is not in the repository (deploy/maps/update-map.sh on the server)

  await admin.goto(url);
  await settled(admin);
  const sum = admin.locator('[data-sum]');
  await expect(sum).toContainText('6 نقطة');
  await expect(sum.locator('[data-off-duty]')).toContainText('4 نقطة');
  await expect(sum.locator('[data-off-duty]')).toContainText('2.22 كم'); // the two before his day and the two after it
  await expect(sum.locator('[data-off-hidden]')).toHaveCount(0);

  // a user with the routes but not the driver's own time
  const role = await api.post('/roles', { code: 'routes' + n, name: { ar: 'مسارات ' + n, en: 'Routes ' + n }, permissions: ['tracking.history', 'tracking.live'] });
  await api.post('/users', { username: 'routes' + n, full_name: 'مراقب ' + n, password: 'routes-password-' + n, role_codes: [role.code], all_companies: true });
  const ctx = await browser.newContext({ baseURL, locale: 'ar' });
  const page = await ctx.newPage();
  await page.goto('/login.html');
  await page.fill('#u', 'routes' + n);
  await page.fill('#p', 'routes-password-' + n);
  await page.click('#step1 [type=submit]');
  await page.waitForURL(/admin\.html/);
  await page.goto(url);
  const his = page.locator('[data-sum]');
  await expect(his).toContainText('2 نقطة');
  await expect(his.locator('[data-off-hidden]')).toContainText('4 نقطة خارج يوم العمل');
  await expect(his.locator('[data-off-duty]')).toHaveCount(0);
  await ctx.close();
});
