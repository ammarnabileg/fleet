// The live map never shows an old position as a current one (each vehicle says how old its last position is, and a
// silent one says "signal lost"), follows the stream, fits and follows vehicles, switches list/map on a phone; the
// route shows its stops and GPS gaps and plays back; the integrations page tells a channel's state, its last
// connection test and the messages that went out apart.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

async function fleetWithPhones(api, n, count) {
  const company = await api.post('/companies', { name: { ar: 'شركة الخريطة ' + n, en: 'Map company ' + n } });
  const out = [];
  for (let i = 0; i < count; i++) {
    const vehicle = await api.post('/vehicles', { plate_number: (7 + i) + '/' + n.slice(-5), company_id: company.id, last_odometer_km: 1000 });
    const driver = await api.post('/employees', {
      employee_number: 'MP' + uid(), name: { ar: 'سائق الخريطة ' + i + ' ' + n, en: 'Map driver ' + i }, company_id: company.id, is_driver: true, phone: phone(),
    });
    await api.post('/custodies', {
      vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 1000, photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()),
      started_at: new Date(Date.now() - 3 * 3600e3).toISOString(),
    });
    const app = await api.driverPhone(driver.id, 'map-' + n + '-' + i);
    let seq = 0;
    const send = (list) => app.call('POST', '/driver/positions', {
      sent_at: new Date().toISOString(),
      points: list.map(([min, lat, lng]) => ({ seq: ++seq, recorded_at: new Date(Date.now() - min * 60e3).toISOString(), lat, lng: lng || 47.98, speed_kmh: 30 })),
    });
    out.push({ vehicle, driver, send });
  }
  return { company, cars: out };
}

test('the live map ages every position, follows the stream and switches list/map on a phone', async ({ admin, api }) => {
  admin.allow(/\/maps\//); // no map file on the test server: the fallback map, and its status file is missing
  const n = uid();
  const { cars: [fresh, silent] } = await fleetWithPhones(api, n, 2);
  await fresh.send([[0.2, 29.37]]);
  await silent.send([[30, 29.33]]); // 30 minutes ago: older than the 10-minute signal loss setting

  await admin.goto('/admin.html#/tracking');
  await settled(admin);
  const item = (car) => admin.locator(`[data-veh="${car.vehicle.id}"]`);
  await expect(item(fresh).locator('[data-veh-state]')).toContainText('يرسل · آخر موقع منذ');
  await expect(item(silent).locator('[data-veh-state]')).toContainText(/انقطاع · آخر موقع معروف منذ 3\d د/);
  await expect(admin.locator('[data-live-state]')).toHaveAttribute('data-stream', 'live');

  // a new position arrives through the stream: current again, without reloading
  await silent.send([[0, 29.34]]);
  await expect(item(silent).locator('[data-veh-state]')).toContainText('يرسل', { timeout: 10_000 });
  await expect(admin.locator('[data-live-state]')).toContainText('آخر موقع وصل');

  const tools = admin.locator('.trk-tools');
  if (await tools.count()) { // the map loaded (WebGL): its own buttons
    await expect(tools.locator('[data-follow]')).toBeDisabled(); // nothing selected yet
    await item(fresh).click(); // choosing a vehicle flies to it and follows it
    await expect(tools.locator('[data-follow]')).toHaveAttribute('aria-pressed', 'true');
    await tools.locator('[data-follow]').click();
    await expect(tools.locator('[data-follow]')).toHaveAttribute('aria-pressed', 'false');
    await admin.locator('[data-veh-mark]').last().click(); // and so does a car on the map (the top one)
    await expect(tools.locator('[data-follow]')).toHaveAttribute('aria-pressed', 'true');
    await tools.locator('[data-fit]').click();
    await expect(tools.locator('[data-follow]')).toHaveAttribute('aria-pressed', 'false');
    await expect(admin.locator('[data-veh-mark]').first()).toHaveAttribute('title', /آخر موقع/);
    await expect(admin.locator('[data-map-fallback]')).toHaveAttribute('data-state', 'none');
    await expect(admin.locator('[data-map-fallback]')).toContainText('خدمة الخرائط');
  }

  // a phone: one pane at a time, list or map
  await admin.setViewportSize({ width: 390, height: 844 });
  const map = admin.locator('[data-map-wrap]'), list = admin.locator('.trk-side');
  await admin.locator('[data-pane-btn="list"]').click();
  await expect(list).toBeVisible();
  await expect(map).toBeHidden();
  await item(silent).click(); // choosing a vehicle shows it on the map
  await expect(map).toBeVisible();
  await expect(list).toBeHidden();
  await expect(admin.locator('[data-pane-btn="map"]')).toHaveAttribute('aria-pressed', 'true');
});

test('the route lists its stops and GPS gaps and plays back', async ({ admin, api }) => {
  admin.allow(/\/maps\//);
  const n = uid();
  const { cars: [car] } = await fleetWithPhones(api, n, 1);
  const pts = [];
  for (let m = 100; m >= 96; m--) pts.push([m, 29.30 + (100 - m) * 0.01]); // driving
  for (let m = 95; m >= 88; m--) pts.push([m, 29.34]); // standing 8 minutes
  pts.push([86, 29.36], [60, 29.37], [58, 29.38]); // then 26 minutes without a position
  await car.send(pts);

  await admin.goto(`/admin.html#/tracking?route=${car.vehicle.id}`);
  await settled(admin);
  const sum = admin.locator('[data-sum]');
  await expect(sum.locator('[data-stops]')).toContainText('1 توقف');
  await expect(sum.locator('[data-gaps]')).toContainText('1 فجوة GPS');
  const events = admin.locator('[data-events] [data-event]');
  await expect(events).toHaveCount(2);
  await expect(events.nth(0)).toContainText('توقف 8 دقيقة');
  await expect(events.nth(1)).toContainText('فجوة GPS 26 دقيقة');

  // the slider moves through the route: inside the gap it says so instead of drawing a made-up position
  const pos = admin.locator('[data-play-pos]');
  await expect(pos).toBeVisible();
  const max = Number(await pos.getAttribute('max'));
  expect(max).toBeGreaterThan(40 * 60);
  await pos.evaluate((el, v) => { el.value = String(v); el.dispatchEvent(new Event('input', { bubbles: true })); }, 14 * 60 + 13 * 60);
  await expect(admin.locator('[data-play-now]')).toContainText('فجوة GPS');
  await pos.evaluate((el, v) => { el.value = String(v); el.dispatchEvent(new Event('input', { bubbles: true })); }, 8 * 60);
  await expect(admin.locator('[data-play-now]')).toContainText('متوقف');
  await admin.locator('[data-play-btn]').click();
  await expect(admin.locator('[data-play-btn]')).toContainText('إيقاف');
  await admin.locator('[data-play-btn]').click();
  await expect(admin.locator('[data-play-btn]')).toContainText('تشغيل');
});

test('a messaging channel shows its state, its last test and its messages apart', async ({ admin, api }) => {
  const n = uid();
  const driver = await api.post('/employees', {
    employee_number: 'MS' + n, name: { ar: 'سائق الرسائل ' + n, en: 'Messages ' + n },
    company_id: (await api.post('/companies', { name: { ar: 'شركة الرسائل ' + n, en: 'Messages ' + n } })).id, is_driver: true, phone: phone(),
  });
  await api.put(`/employees/${driver.id}/app-access`, { app_access: 'active' });
  await api.post('/driver/auth/otp', { phone: driver.phone, device_uid: 'otp-' + n });

  await admin.goto('/admin.html#/integrations');
  await settled(admin);
  const wa = admin.locator('form[data-kind="whatsapp"]');
  await expect(wa.locator('[data-state]')).toHaveAttribute('data-state', /not_configured|disabled|untested|working|failed/);
  await expect(wa.locator('[data-test-line]')).toContainText('لا يرسل رسالة لأحد');
  const row = wa.locator('[data-messages-table] tbody tr').filter({ hasText: driver.phone.slice(-4) });
  await expect(row).toContainText('رمز دخول السائق');
  await expect(row).toContainText('سجل التطوير'); // the test server's log provider: nothing really sent
  await expect(wa.locator('[data-messages]')).not.toContainText(driver.phone.slice(1)); // only the last digits

  const push = admin.locator('form[data-kind="push"]');
  await expect(push.locator('[data-push-devices]')).toContainText('هواتف مسجلة للإشعارات');
  await expect(push.locator('[data-state]')).toHaveAttribute('data-state', /not_configured|disabled|untested|working|failed/);
});
