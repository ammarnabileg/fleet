// Maintenance asked by the office: in the panel's «طلب صيانة» form the office picks the center, and the request is at
// the center at once. The car stays with its driver at the center; when the office takes it back meanwhile, nobody
// holds it: the center gives its last odometer reading with the invoice, and the office records the pickup.
const { test, expect, uid, phone, settled, jpeg, pdf, centerWithUser, centerSignIn } = require('./fixtures');

const file = (name, mimeType, buffer) => ({ name, mimeType, buffer });

test('the office sends the car to the center it picks; a car nobody holds is collected by the office', async ({ admin, api, portal }) => {
  test.setTimeout(180_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المركز المباشر ' + n, en: 'Direct center company ' + n } });
  const plate = '8/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Toyota', model: 'Yaris', company_id: company.id, last_odometer_km: 51000 });
  const driver = await api.post('/employees', {
    employee_number: 'X' + n, name: { ar: 'سائق المركز ' + n, en: 'Center driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const custody = await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 51000, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
  });
  const { center, username } = await centerWithUser(api, n);

  // ---- the office's form: the vehicle, the center, what is wrong
  const top = (page) => page.locator('.overlay[data-open]').last();
  await admin.goto('/admin.html#/maintenance');
  await settled(admin);
  await admin.click('[data-action="mnt-new"]');
  const m = top(admin);
  await m.locator('[name=vehicle]').fill(plate + ' — Toyota Yaris'); // the vehicle as the list names it
  await m.locator('[name=center]').selectOption(center.id);
  await m.locator('[name=kind]').selectOption('electrical');
  await m.locator('[name=desc]').fill('البطارية لا تشحن');
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  const listed = await api.get('/maintenance/requests?vehicle_id=' + vehicle.id);
  expect(listed.map((r) => [r.status, r.source, r.center && r.center.name])).toEqual([['referred', 'office', center.name]]);
  const rid = listed[0].id;
  await expect(admin.locator('.timeline .tl-t')).toHaveText(['طلب من المكتب إلى ' + center.name]);

  // ---- the center receives the car: it stays with its driver
  await centerSignIn(portal, username);
  await portal.goto('/center.html#/r/' + rid);
  await settled(portal);
  const step = async (act, fill) => {
    await portal.click(`[data-act="${act}"]`);
    const d = top(portal);
    if (fill) await fill(d);
    await d.locator('button[type=submit]').click();
    await expect(d).toBeHidden();
  };
  await step('receive', async (d) => {
    await d.locator('[name=km]').fill('51040');
    await d.locator('[name=odo]').setInputFiles(file('odo.jpg', 'image/jpeg', jpeg()));
  });
  await expect(portal.locator('[data-in-custody]')).toBeVisible();
  expect((await api.get('/custodies/' + custody.id)).ended_at).toBeNull();

  // ---- the office takes the car back from the driver while it is at the center: nobody holds it now
  await api.post('/custodies/' + custody.id + '/return', { odometer_km: 51040, photo_sha256: await api.upload('ret.jpg', 'image/jpeg', jpeg()) });
  expect((await api.get('/vehicles/' + vehicle.id)).status).toBe('maintenance');

  // ---- ready with the invoice and the last reading (the next handover is compared with it)
  await portal.reload();
  await settled(portal);
  await step('ready', async (d) => {
    await d.locator('[name=number]').fill('DC-' + n);
    await d.locator('[name=total]').fill('35');
    await d.locator('[name=file]').setInputFiles(file('invoice.pdf', 'application/pdf', pdf()));
    await d.locator('[name=km]').fill('51042');
    await d.locator('[name=odo]').setInputFiles(file('odo2.jpg', 'image/jpeg', jpeg()));
  });
  await expect.poll(async () => (await api.get('/maintenance/requests/' + rid)).status).toBe('ready');
  expect((await api.get('/maintenance/requests/' + rid)).final_km).toBe(51042);

  // ---- the office records the pickup: the car is available again
  await admin.goto('/admin.html#/maintenance/' + rid);
  await admin.reload();
  await settled(admin);
  await admin.click('[data-action="mnt-picked"]');
  await top(admin).locator('.btn-primary').last().click();
  await expect.poll(async () => (await api.get('/maintenance/requests/' + rid)).status).toBe('picked_up');
  expect((await api.get('/vehicles/' + vehicle.id)).status).toBe('available');

  // ---- finance settles with the center: its invoices alone
  await admin.goto('/admin.html#/maintenance?tab=invoices');
  await settled(admin);
  await admin.locator('[data-inv-center]').selectOption(center.id);
  await settled(admin);
  const rows = admin.locator('[data-p="invoices"] tbody tr');
  await expect(rows.filter({ hasText: 'DC-' + n })).toHaveCount(1);
  await expect(rows.filter({ hasNotText: center.name })).toHaveCount(0);
  const invoice = (await api.get('/maintenance/invoices?limit=200')).find((x) => x.number === 'DC-' + n);
  await api.post('/maintenance/invoices/' + invoice.id + '/approve');
  await expect.poll(async () => (await api.get('/maintenance/requests/' + rid)).status).toBe('closed');

  // ---- the old switch is gone from the settings: every request goes straight to the center
  await admin.goto('/admin.html#/settings?tab=system');
  await settled(admin);
  await expect(admin.locator('form[data-sec="maintenance"]')).toBeVisible();
  await expect(admin.locator('#view')).not.toContainText('طلب الصيانة يذهب من السائق مباشرة إلى المركز');
});
