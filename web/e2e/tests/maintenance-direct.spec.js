// Maintenance straight to the center (settings: maintenance.direct_to_center): the driver picks the center in the
// app, the center works without a quote, uploads its invoice and then calls the driver, who collects the car in the
// app and has it back; the office only follows, and finance approves the invoice when it settles with the center.
const { test, expect, uid, phone, settled, jpeg, pdf, centerWithUser, centerSignIn } = require('./fixtures');

const file = (name, mimeType, buffer) => ({ name, mimeType, buffer });

async function direct(api, on) {
  const current = (await api.get('/settings')).maintenance;
  await api.put('/settings/maintenance', { version: current.version, value: Object.assign({}, current.value, { direct_to_center: on }) });
}

test('straight to the center: no office step from the request to the car back with the driver', async ({ admin, api, portal }) => {
  test.setTimeout(180_000);
  await direct(api, true);
  try {
    const n = uid();
    const company = await api.post('/companies', { name: { ar: 'شركة المركز المباشر ' + n, en: 'Direct center company ' + n } });
    const plate = '8/' + n.slice(-6);
    const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Toyota', model: 'Yaris', company_id: company.id, last_odometer_km: 51000 });
    const driver = await api.post('/employees', {
      employee_number: 'X' + n, name: { ar: 'سائق المركز ' + n, en: 'Center driver ' + n },
      company_id: company.id, is_driver: true, phone: phone(),
    });
    await api.post('/custodies', {
      vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 51000, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
      started_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
    });
    const { center, username } = await centerWithUser(api, n);

    // ---- the driver picks the center: the request is at the center at once
    const app = await api.driverPhone(driver.id, 'e2e-' + n);
    const form = await app.call('GET', '/driver/maintenance/form');
    expect(form.direct_to_center).toBe(true);
    expect(form.centers.map((c) => c.id)).toContain(center.id);
    const asked = await app.call('POST', '/driver/maintenance', {
      client_ref: require('crypto').randomUUID(), kind: 'electrical', description: 'البطارية لا تشحن',
      photos: [await app.photo('camera')], center_id: center.id,
    });
    expect(asked.status).toBe('referred');

    // ---- the center: reception, the repair without a quote, done, the invoice, then the driver is called
    const top = (page) => page.locator('.overlay[data-open]').last();
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
    await step('receive', async (m) => {
      await m.locator('[name=km]').fill('51040');
      await m.locator('[name=odo]').setInputFiles(file('odo.jpg', 'image/jpeg', jpeg()));
    });
    await expect(portal.locator('[data-act="quote"]')).toHaveText(/اختياري/);
    await step('start_repair');
    await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('in_repair');
    await step('complete', async (m) => {
      await m.locator('[name=details]').fill('تم تغيير البطارية');
      await m.locator('[name=km]').fill('51042');
      await m.locator('[name=odo]').setInputFiles(file('odo2.jpg', 'image/jpeg', jpeg()));
    });
    await expect(portal.locator('[data-direct-hint]')).toContainText('أدخل فاتورة الصيانة');
    await expect(portal.locator('[data-act="ready"]')).toHaveCount(0); // the invoice first
    await step('invoice', async (m) => {
      await m.locator('[name=number]').fill('DC-' + n);
      await m.locator('[name=file]').setInputFiles(file('invoice.pdf', 'application/pdf', pdf()));
      await m.locator('[data-k=d]').fill('بطارية');
      await m.locator('[data-k=p]').fill('35');
    });
    await step('ready');
    await expect(portal.locator('[data-act="picked"]')).toHaveCount(0); // the driver confirms it
    await expect(portal.locator('[data-direct-hint]')).toContainText('يؤكد الاستلام من تطبيقه');

    // ---- the driver collects it: the car is his again
    const collected = await app.call('POST', '/driver/maintenance/' + asked.id + '/picked-up', {
      odometer_km: 51050, odometer_photo: await app.photo('camera'), picked_up_at: new Date().toISOString(),
    });
    expect(collected.status).toBe('picked_up');
    expect((await app.call('GET', '/driver/today')).custody.plate_number).toBe(plate);

    // ---- the office sees the whole way; finance approves the center's invoice and the request closes
    await admin.goto('/admin.html#/maintenance/' + asked.id);
    await settled(admin);
    await expect(admin.locator('#view')).toContainText(center.name);
    await expect(admin.locator('[data-action="mnt-approve"]')).toHaveCount(0);
    // finance settles with the center: its invoices alone
    await admin.goto('/admin.html#/maintenance?tab=invoices');
    await settled(admin);
    await admin.locator('[data-inv-center]').selectOption(center.id);
    await settled(admin);
    const rows = admin.locator('[data-p="invoices"] tbody tr');
    await expect(rows.filter({ hasText: 'DC-' + n })).toHaveCount(1);
    await expect(rows.filter({ hasNotText: center.name })).toHaveCount(0);
    const invoice = (await api.get('/maintenance/invoices?limit=200')).find((x) => x.number === 'DC-' + n);
    await api.post('/maintenance/invoices/' + invoice.id + '/approve');
    await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('closed');

    // ---- the switch, where the office turns it on or off
    await admin.goto('/admin.html#/settings?tab=system');
    await settled(admin);
    await expect(admin.locator('#view')).toContainText('طلب الصيانة يذهب من السائق مباشرة إلى المركز');
  } finally {
    await direct(api, false); // the setting is global: the other maintenance specs expect the office's way
  }
});
