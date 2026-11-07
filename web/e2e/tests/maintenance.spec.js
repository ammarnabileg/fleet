// Maintenance, the simple flow, each side in its own browser: the driver asks from his phone and picks the center, the
// request is at the center at once (no approval, no referral); the center receives the car, which stays in the
// driver's custody; the center marks it ready with its invoice; the management approves the invoice; the driver
// collects the car from his phone; the timeline shows only those steps. Finance then pays the center.
const { test, expect, uid, phone, settled, jpeg, pdf, centerWithUser, centerSignIn, kuwaitInput } = require('./fixtures');

// neither computer set to Kuwait time: the arrival time the center types is still Kuwait's
test.use({ timezoneId: 'UTC' });

const file = (name, mimeType, buffer) => ({ name, mimeType, buffer });

test('a repair from the driver\'s request to the car back with him and the paid invoice', async ({ admin, api, portal }) => {
  test.setTimeout(180_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الصيانة ' + n, en: 'Maintenance company ' + n } });
  const plate = '9/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Nissan', model: 'Sunny', company_id: company.id, last_odometer_km: 48000 });
  const driver = await api.post('/employees', {
    employee_number: 'W' + n, name: { ar: 'سائق الصيانة ' + n, en: 'Maintenance driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 48100, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
  });
  const { center, username } = await centerWithUser(api, n);

  // ---- the driver asks from his phone, picks the center: it is there at once
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const form = await app.call('GET', '/driver/maintenance/form');
  expect(form.centers.map((c) => c.id)).toContain(center.id);
  const asked = await app.call('POST', '/driver/maintenance', {
    client_ref: require('crypto').randomUUID(), kind: 'mechanical', description: 'صوت من العجلة الأمامية',
    odometer_km: 48150, photos: [await app.photo('camera')], center_id: center.id,
  });
  expect([asked.status, asked.center.name]).toEqual(['referred', center.name]);

  // ---- the office only follows: no approval or referral to give
  const top = (page) => page.locator('.overlay[data-open]').last();
  await admin.goto('/admin.html#/maintenance/' + asked.id);
  await settled(admin);
  await expect(admin.locator('#view')).toContainText(center.name);
  await expect(admin.locator('[data-action="mnt-approve"]')).toHaveCount(0);
  await expect(admin.locator('[data-action="mnt-picked"]')).toHaveCount(0);

  // ---- the center: first sign-in changes the password, then the request
  await centerSignIn(portal, username);
  await portal.goto('/center.html#/r/' + asked.id);
  await settled(portal);
  const step = async (act, fill) => {
    await portal.click(`[data-act="${act}"]`);
    const m = top(portal);
    if (fill) await fill(m);
    await m.locator('button[type=submit]').click();
    await expect(m).toBeHidden();
  };
  // no step between the reception and ready: no inspection, quote or repair status
  for (const act of ['inspection', 'quote', 'complete', 'ready', 'picked']) await expect(portal.locator(`[data-act="${act}"]`)).toHaveCount(0);
  const arrived = kuwaitInput(Date.now() - 60e3); // a minute ago, as the center types it
  await step('receive', async (m) => {
    await m.locator('[name=at]').fill(arrived);
    await m.locator('[name=km]').fill('48210');
    await m.locator('[name=odo]').setInputFiles(file('odo.jpg', 'image/jpeg', jpeg()));
    await m.locator('[name=ph]').setInputFiles([file('front.jpg', 'image/jpeg', jpeg()), file('left.jpg', 'image/jpeg', jpeg())]);
    await m.locator('[name=cond]').fill('خدش بسيط في الباب الخلفي');
  });
  const received = (await api.get('/maintenance/requests/' + asked.id)).received_at;
  expect(new Date(received).toISOString()).toBe(new Date(arrived + ':00+03:00').toISOString()); // Kuwait time
  await expect(portal.locator('[data-act="ready"]')).toBeVisible();
  for (const act of ['inspection', 'quote', 'complete', 'picked']) await expect(portal.locator(`[data-act="${act}"]`)).toHaveCount(0);

  // the car stays his, "in maintenance", and he cannot start a work day with it
  expect((await api.get('/vehicles/' + vehicle.id)).status).toBe('maintenance');
  const atCenter = await app.call('GET', '/driver/today');
  expect([atCenter.custody.plate_number, atCenter.custody.in_maintenance, atCenter.custody.maintenance_center]).toEqual([plate, true, center.name]);
  await expect(app.call('POST', '/driver/odometer', {
    kind: 'start_day', value_km: 48210, photo_sha256: await app.photo('camera'), recorded_at: new Date().toISOString(),
  })).rejects.toThrow(/409.*vehicle_in_maintenance/);

  // ---- ready for pickup, in one step with the invoice
  await step('ready', async (m) => {
    await m.locator('[name=number]').fill('NR-' + n);
    await m.locator('[name=total]').fill('255');
    await m.locator('[name=file]').setInputFiles(file('invoice.pdf', 'application/pdf', pdf()));
    await m.locator('[name=notes]').fill('تغيير رولمان البلي الأمامي');
  });
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('ready');
  await expect(portal.locator('[data-act="picked"]')).toHaveCount(0); // the driver confirms it
  await expect(portal.locator('[data-direct-hint]')).toContainText('يؤكد الاستلام من تطبيقه');
  const mine = (await app.call('GET', '/driver/maintenance')).find((x) => x.id === asked.id);
  expect([mine.status, mine.pickup_in_app]).toEqual(['ready', true]); // "your car is ready" on his phone

  // ---- the management approves the invoice (it decides the payment, not the pickup)
  await admin.goto('/admin.html#/maintenance?tab=invoices');
  await admin.reload();
  await settled(admin);
  await admin.locator('[data-p="invoices"] tbody tr', { hasText: 'NR-' + n }).locator('td').first().click(); // not its request's link
  await expect(top(admin)).toContainText('255.000');
  await top(admin).locator('.btn-primary', { hasText: 'اعتماد' }).click();
  await top(admin).locator('.btn-primary').last().click();
  const invoice = async () => (await api.get('/maintenance/invoices?limit=200')).find((x) => x.number === 'NR-' + n);
  await expect.poll(async () => (await invoice()).status).toBe('approved');
  expect((await api.get('/maintenance/requests/' + asked.id)).status).toBe('ready');

  // ---- the driver collects it: his reading, the same custody; his day can start; the request closes
  const collected = await app.call('POST', '/driver/maintenance/' + asked.id + '/picked-up', {
    odometer_km: 48240, odometer_photo: await app.photo('camera'), picked_up_at: new Date().toISOString(),
  });
  expect(collected.status).toBe('closed');
  const back = await app.call('GET', '/driver/today');
  expect([back.custody.id, back.custody.in_maintenance, back.custody.last_odometer_km]).toEqual([atCenter.custody.id, false, 48240]);
  expect((await api.get('/vehicles/' + vehicle.id)).status).toBe('assigned');

  // ---- the timeline: the request to the center, received, ready with its invoice, collected
  const steps = ['طلب من السائق إلى ' + center.name, 'مستلمة', 'جاهزة للاستلام', 'تم الاستلام', 'مغلق'];
  await admin.goto('/admin.html#/maintenance/' + asked.id);
  await admin.reload();
  await settled(admin);
  await expect(admin.locator('.timeline .tl-t')).toHaveText(steps);
  await expect(admin.locator('[data-tl-invoice]')).toContainText('NR-' + n);
  await expect(admin.locator('[data-tl-invoice]')).toContainText('معتمدة');
  await portal.reload();
  await settled(portal);
  await expect(portal.locator('.timeline .tl-t')).toHaveText(steps);

  // ---- finance pays the center
  await admin.goto('/admin.html#/maintenance?tab=invoices');
  await admin.reload();
  await settled(admin);
  await admin.locator('[data-p="invoices"] .chip', { hasText: 'معتمدة غير مدفوعة' }).click();
  await settled(admin);
  await admin.locator('[data-p="invoices"] tbody tr', { hasText: 'NR-' + n }).locator('td').first().click(); // not its request's link
  await top(admin).locator('.btn-primary', { hasText: 'تسجيل الدفع' }).click();
  await top(admin).locator('[name=ref]').fill('TRX-' + n);
  await top(admin).locator('button[type=submit]').click();
  await expect.poll(async () => (await invoice()).payment_status).toBe('paid');
  const final = await invoice();
  expect([final.status, final.total, final.request && final.request.id, final.payment_ref]).toEqual(['approved', '255.000', asked.id, 'TRX-' + n]);
  const detail = await api.get('/maintenance/requests/' + asked.id);
  // the driver's photo; at reception two photos and the odometer
  expect(detail.photos.map((x) => x.stage)).toEqual(['request', 'reception', 'reception', 'reception']);
  expect(detail.quotes).toEqual([]);

  // ---- the two sides stay apart: the center's session reaches none of the company's data
  for (const path of ['/employees', '/vehicles', '/maintenance/requests', '/payroll/runs']) {
    const r = await portal.context().request.get('/api/v1' + path);
    expect([path, r.status()]).toEqual([path, 403]);
  }
});
