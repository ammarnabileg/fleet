// A car taken from one driver for another, from the handover dialog: released (the holder leaves it) or swapped (the
// two drivers exchange cars), said before it is done; and a car a driver registered from the app, approved from the
// custody page, which becomes his custody with his reading.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

const photo = (name) => ({ name: name + '.jpg', mimeType: 'image/jpeg', buffer: jpeg() });

async function setup(api, n) {
  const company = await api.post('/companies', { name: { ar: 'شركة التبديل ' + n, en: 'Swap company ' + n } });
  const driver = (tag) => api.post('/employees', {
    employee_number: tag + n, name: { ar: 'سائق ' + tag + ' ' + n, en: 'Driver ' + tag + ' ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const car = (tag, km) => api.post('/vehicles', { plate_number: tag + '-' + n.slice(-6), company_id: company.id, last_odometer_km: km });
  const hold = async (vehicle, d) => api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: d.id, odometer_km: vehicle.last_odometer_km,
    photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()), started_at: new Date(Date.now() - 3600e3).toISOString(),
  });
  return { company, driver, car, hold };
}

async function openHandover(admin, vehicle, holder, driver) {
  await admin.goto('/admin.html#/custody');
  await settled(admin);
  await admin.getByRole('button', { name: 'تسليم سيارة لسائق' }).click();
  const dlg = admin.locator('.overlay[data-open]').last();
  await dlg.locator('[name=vehicle]').fill(vehicle.plate_number + (holder ? ' · مع ' + holder.name.ar : ''));
  await dlg.locator('[name=driver]').fill(driver.label);
  return dlg;
}

const label = (d, plate) => Object.assign(d, { label: d.name.ar + ' — ' + d.employee_number + (plate ? ' · معه ' + plate : '') });

test('a held car released to another driver: the holder leaves it, one reading', async ({ admin, api }) => {
  const n = uid();
  const { driver, car, hold } = await setup(api, n);
  const x = await car('X', 50000);
  const b = await driver('B');
  const a = label(await driver('A'));
  await hold(x, b);
  const phoneB = await api.driverPhone(b.id, 'e2e-b-' + n);

  const dlg = await openHandover(admin, x, b, a);
  await expect(dlg.locator('[data-transfer-text]')).toContainText('مع ' + b.name.ar);
  await expect(dlg.locator('[data-transfer-text]')).toContainText('هيخرّج');
  await expect(dlg.locator('[data-other]')).toBeHidden();
  await dlg.locator('[name=odometer_km]').fill('50040');
  await dlg.locator('input[name=odo_photo]').setInputFiles(photo('odo'));
  await dlg.locator('button[type=submit]').click();
  const confirm = admin.locator('.overlay[data-open]').last();
  await expect(confirm.locator('[data-confirm-outcome]')).toContainText(a.name.ar + ' ياخد ' + x.plate_number);
  await expect(confirm.locator('[data-confirm-outcome]')).toContainText(b.name.ar + ' يفضل من غير عربية');
  await confirm.getByRole('button', { name: 'تسليم' }).click();
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  const open = (await api.get('/custodies?open=true&limit=200')).filter((c) => c.vehicle.id === x.id);
  expect(open.map((c) => c.driver.id)).toEqual([a.id]);
  const readings = await api.get('/odometer/readings?vehicle_id=' + x.id);
  expect(readings.slice(0, 2).map((r) => [r.kind, r.value_km, r.flags])).toEqual([['handover', 50040, []], ['return', 50040, []]]);
  expect((await phoneB.call('GET', '/driver/vehicle')).vehicle).toBeNull();
  const told = (await phoneB.call('GET', '/driver/notifications')).items.map((x) => x.kind);
  expect(told[0]).toBe('vehicle_taken');
});

test('two drivers swap cars: each car read once, both readings asked for', async ({ admin, api }) => {
  const n = uid();
  const { driver, car, hold } = await setup(api, n);
  const x = await car('X', 30000);
  const y = await car('Y', 40000);
  const b = await driver('B');
  const a = label(await driver('A'), y.plate_number);
  await hold(x, b);
  await hold(y, a);

  const dlg = await openHandover(admin, x, b, a);
  await expect(dlg.locator('[data-transfer-text]')).toContainText(a.name.ar + ' معاه ' + y.plate_number);
  await expect(dlg.locator('[data-other]')).toBeVisible();
  await expect(dlg.locator('[name=other_odometer_km]')).toHaveValue('40000');
  await expect(dlg.locator('[name=mode][value=swap]')).toBeChecked();
  await expect(dlg.locator('[data-outcome]')).toContainText(b.name.ar + ' ياخد ' + y.plate_number);
  await dlg.locator('[name=odometer_km]').fill('30050');
  await dlg.locator('input[name=odo_photo]').setInputFiles(photo('odo-x'));
  await dlg.locator('[name=other_odometer_km]').fill('40070');
  await dlg.locator('input[name=other_odo_photo]').setInputFiles(photo('odo-y'));
  await dlg.locator('button[type=submit]').click();
  const confirm = admin.locator('.overlay[data-open]').last();
  await expect(confirm.locator('[data-confirm-outcome]')).toContainText(a.name.ar + ' ياخد ' + x.plate_number);
  await confirm.getByRole('button', { name: 'تسليم' }).click();
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  const open = await api.get('/custodies?open=true&limit=200');
  const holder = (v) => open.filter((c) => c.vehicle.id === v.id).map((c) => c.driver.id);
  expect([holder(x), holder(y)]).toEqual([[a.id], [b.id]]);
  for (const [v, km] of [[x, 30050], [y, 40070]]) {
    const readings = await api.get('/odometer/readings?vehicle_id=' + v.id);
    expect(readings.slice(0, 2).map((r) => [r.kind, r.value_km, r.flags])).toEqual([['handover', km, []], ['return', km, []]]);
  }
});

test('a car registered from the app waits, then the office approves it', async ({ admin, api }) => {
  const n = uid();
  const { driver, car } = await setup(api, n);
  const v = await car('C', 7000);
  const d = await driver('D');
  const app = await api.driverPhone(d.id, 'e2e-d-' + n);
  const mine = await app.call('POST', '/driver/vehicle-claims', {
    plate: v.plate_number, odometer_km: 7015, photo_sha256: await app.photo('camera'),
    recorded_at: new Date(Date.now() - 60e3).toISOString(), client_ref: require('crypto').randomUUID(),
  });
  expect(mine.claim.status).toBe('pending');

  await admin.goto('/admin.html#/custody');
  await settled(admin);
  const row = admin.locator('[data-pending=vehicle-claims] [data-pending-id]', { hasText: d.name.ar });
  await expect(row).toContainText(v.plate_number);
  await expect(row.locator('[data-claim-km]')).toContainText('7,015');
  await expect(row.locator('[data-thumbs] img')).toHaveCount(1);
  await row.getByRole('button', { name: 'موافقة' }).click();
  await admin.locator('.overlay[data-open]').last().getByRole('button', { name: 'موافقة' }).click();
  await expect(row).toBeHidden();

  const now = await app.call('GET', '/driver/vehicle');
  expect([now.vehicle.plate_number, now.vehicle.last_odometer_km]).toEqual([v.plate_number, 7015]);
  const open = (await api.get('/custodies?open=true&limit=200')).find((c) => c.vehicle.id === v.id);
  expect(open.driver.id).toBe(d.id);
});

test('a car handed to the driver who holds it: said, and nothing is sent', async ({ admin, api }) => {
  const n = uid();
  const { driver, car, hold } = await setup(api, n);
  const x = await car('X', 9000);
  const a = await driver('A');
  await hold(x, a);
  label(a, x.plate_number);
  const sent = [];
  admin.on('request', (r) => { if (r.url().includes('/custodies/transfer') && r.method() === 'POST') sent.push(r.url()); });
  const dlg = await openHandover(admin, x, a, a);
  await expect(dlg.locator('[data-transfer-same]')).toContainText(a.name.ar + ' معاه العربية ' + x.plate_number);
  await dlg.locator('input[name=odo_photo]').setInputFiles(photo('odo'));
  await dlg.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('بالفعل');
  await expect(dlg).toBeVisible();
  expect(sent).toEqual([]);
  expect((await api.get('/custodies?open=true&limit=200')).filter((c) => c.vehicle.id === x.id).map((c) => c.driver.id)).toEqual([a.id]);
});
