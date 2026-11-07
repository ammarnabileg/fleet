// Maintenance plans in the panel: a periodic schedule by distance, the request made from it, its follow-up (priority,
// expected date), a replacement car while the driver's own is at the center (a custody of its own, linked both ways),
// handed back in the same step as he collects his own car; the schedule is then done at his reading.
// And fuel economy: litres per 100 km from consecutive fills of a car, and what could not be counted.
const { test, expect, uid, phone, settled, jpeg, pdf, centerWithUser, centerSignIn } = require('./fixtures');

const file = (name, mimeType, buffer) => ({ name, mimeType, buffer });
const day = (offset) => new Date(Date.now() + 3 * 3600e3 + offset * 86400e3).toISOString().slice(0, 10);

test('a schedule by distance, its request, a replacement car linked both ways, done at the pickup', async ({ admin, api, portal }) => {
  test.setTimeout(240_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الخطط ' + n, en: 'Plans company ' + n } });
  const plate = '6/' + n.slice(-6), sparePlate = '5/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Kia', model: 'Pegas', company_id: company.id, last_odometer_km: 30000 });
  const spare = await api.post('/vehicles', { plate_number: sparePlate, make: 'Kia', model: 'Rio', company_id: company.id, last_odometer_km: 1000 });
  const driver = await api.post('/employees', {
    employee_number: 'P' + n, name: { ar: 'سائق الخطة ' + n, en: 'Plan driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 30000, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
  });
  const { center, username } = await centerWithUser(api, n);
  const top = (page) => page.locator('.overlay[data-open]').last();

  // ---- the schedule: every 5,000 km, last done at 26,000: due at 31,000, 1,000 km left (due soon)
  await admin.goto('/admin.html#/maintenance?tab=schedules');
  await settled(admin);
  await admin.click('[data-sch-new]');
  let m = top(admin);
  await m.locator('[name=vehicle]').fill(plate + ' — Kia Pegas');
  await m.locator('[name=title]').fill('تغيير الزيت ' + n);
  await m.locator('[name=km]').fill('5000');
  await m.locator('[name=last_km]').fill('26000');
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  const row = admin.locator('#view [data-panel=schedules] tbody tr', { hasText: 'تغيير الزيت ' + n });
  await expect(row.locator('[data-sch-state]')).toHaveAttribute('data-sch-state', 'due');
  await expect(row).toContainText('31,000');

  // ---- a request for it, from its drawer: the center, the expected date
  await row.click();
  await top(admin).getByRole('button', { name: 'طلب صيانة لها' }).click();
  m = top(admin);
  await m.locator('[name=center]').selectOption(center.id);
  await m.locator('[name=expected]').fill(day(2));
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  await expect(admin).toHaveURL(/#\/maintenance\/[0-9a-f-]+$/);
  const rid = admin.url().split('/').pop();
  await settled(admin);
  await expect(admin.locator('#view')).toContainText('ضمن الصيانة الدورية');
  await expect(admin.locator('#view')).toContainText('تغيير الزيت ' + n);

  // ---- the center receives the car: it stays with its driver
  await centerSignIn(portal, username);
  await portal.goto('/center.html#/r/' + rid);
  await settled(portal);
  await portal.click('[data-act="receive"]');
  m = top(portal);
  await m.locator('[name=km]').fill('30050');
  await m.locator('[name=odo]').setInputFiles(file('odo.jpg', 'image/jpeg', jpeg()));
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();

  // ---- the follow-up: urgent
  await admin.reload();
  await settled(admin);
  await admin.click('[data-action="mnt-plan"]');
  m = top(admin);
  await m.locator('[name=priority]').selectOption('urgent');
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  await expect(admin.locator('#view')).toContainText('عاجلة');

  // ---- a replacement car while his own is at the center: a custody of its own kind, linked from the request
  await admin.click('[data-action="mnt-spare"]');
  m = top(admin);
  await m.locator('[name=spare]').fill(sparePlate + ' — Kia Rio');
  await m.locator('[name=km]').fill('1000');
  await m.locator('[name=odo]').setInputFiles(file('spare.jpg', 'image/jpeg', jpeg()));
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  const links = admin.locator('#view [data-mnt-links]');
  await expect(links).toContainText('سيارة بديلة');
  await expect(links).toContainText(sparePlate);
  expect((await api.get('/vehicles/' + spare.id)).status).toBe('assigned');
  // and from the replacement's custody back to the request
  await links.locator('[data-custody-open]', { hasText: sparePlate }).click();
  const drawer = top(admin);
  await expect(drawer.locator('[data-custody-mnt]')).toContainText('بديلة عن ' + plate);
  await drawer.getByRole('button', { name: 'إغلاق' }).last().click();

  // ---- ready; the driver collects his car and hands the replacement back in the same step, from his phone
  await portal.reload();
  await settled(portal);
  await portal.click('[data-act="ready"]');
  m = top(portal);
  await m.locator('[name=number]').fill('PL-' + n);
  await m.locator('[name=total]').fill('12');
  await m.locator('[name=file]').setInputFiles(file('invoice.pdf', 'application/pdf', pdf()));
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  const app = await api.driverPhone(driver.id, 'e2e-plan-' + n);
  const [mine] = (await app.call('GET', '/driver/maintenance')).filter((r) => r.id === rid);
  expect([mine.pickup_in_app, mine.replacement_plate]).toEqual([true, sparePlate]);
  await app.call('POST', `/driver/maintenance/${rid}/picked-up`, {
    odometer_km: 30060, odometer_photo: await app.photo('camera'), picked_up_at: new Date().toISOString(),
    replacement_odometer_km: 1040, replacement_odometer_photo: await app.photo('camera'),
  });
  expect((await api.get('/vehicles/' + spare.id)).status).toBe('available');
  await admin.reload();
  await settled(admin);
  await expect(links).toContainText('الاستلام من المركز');
  await expect(links.locator('[data-custody-open]', { hasText: sparePlate })).not.toContainText('مفتوحة');

  // ---- the schedule is done at his reading: ok again, due at 35,060
  await admin.goto('/admin.html#/maintenance?tab=schedules');
  await settled(admin);
  await admin.locator('#view [data-panel=schedules] [data-chip=""]').click();
  await expect(row.locator('[data-sch-state]')).toHaveAttribute('data-sch-state', 'ok');
  await expect(row).toContainText('35,060');
});

test('fuel economy: litres per 100 km from consecutive fills, with what could not be counted', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الاستهلاك ' + n, en: 'Economy company ' + n } });
  const plate = '4/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, company_id: company.id, last_odometer_km: 50000 });
  const fuel = (await api.get('/finance/expense-types')).find((t) => t.code === 'fuel');
  const fills = [[20, 50000, '40', '4.000'], [15, 50450, '45', '4.500'], [10, 50900, '45', '4.500'], [5, 51300, null, '4.000']];
  for (const [ago, km, litres, amount] of fills) {
    const e = await api.post('/finance/expenses', {
      company_id: company.id, type_id: fuel.id, expense_date: day(-ago), amount, payment_method: 'payable',
      quantity: litres, vehicle_id: vehicle.id, odometer_km: km, supplier: 'محطة ' + n,
    });
    await api.post(`/finance/expenses/${e.id}/approve`, {});
  }
  await admin.goto('/admin.html#/cash?tab=fuel');
  await settled(admin);
  const eco = admin.locator('#view [data-fuel-economy]');
  const car = eco.locator('[data-eco-table] tbody tr', { hasText: plate });
  await expect(car).toContainText('10.00'); // 90 litres over 900 km
  await expect(car).toContainText('900');
  await eco.locator('[data-tab=exceptions]').click();
  const skipped = eco.locator('[data-eco-table] tbody tr', { hasText: plate });
  await expect(skipped).toContainText('بلا لترات');
});
