// What drivers ask for from the app and the office decides (BRD FR-ASG-04, FR-APP-05): a change of vehicle naming
// the other car by its plate (an unknown plate refused), refused with its reason then closed as done, from the custody
// page, and kept in its history with the Excel export; a renewed residence checked against its photo and approved,
// from the documents tab, after which it is the driver's current one.
const fs = require('fs');
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');
const { readXlsx } = require('./xlsx');

test('a change of vehicle refused then done, and a renewed document approved', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الطلبات ' + n, en: 'Requests company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '7/' + n.slice(-6), make: 'Kia', model: 'Rio', company_id: company.id, last_odometer_km: 5000 });
  const other = await api.post('/vehicles', { plate_number: '8-' + n.slice(-6), make: 'Kia', model: 'Pegas', company_id: company.id, last_odometer_km: 100 });
  const driver = await api.post('/employees', {
    employee_number: 'Q' + n, name: { ar: 'سائق الطلبات ' + n, en: 'Requests driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 5000, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 3600e3).toISOString(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- a change of vehicle: an unknown plate refused; refused with the reason, asked again, then closed as done
  await expect(app.call('POST', '/driver/vehicle-change-requests', { requested_plate: '99-' + n.slice(-6), reason: 'المكيف لا يعمل' }))
    .rejects.toThrow(/vehicle_plate_not_found/);
  await app.call('POST', '/driver/vehicle-change-requests', { requested_plate: other.plate_number, reason: 'المكيف لا يعمل' });
  const custodyPage = async () => {
    await admin.goto('/admin.html#/custody');
    await admin.reload();
    await settled(admin);
    return admin.locator('[data-pending=vehicle-changes] [data-pending-id]', { hasText: driver.name.ar });
  };
  let row = await custodyPage();
  await expect(row).toContainText('المكيف لا يعمل');
  await expect(row).toContainText(vehicle.plate_number);
  await expect(row.locator('[data-requested]')).toContainText(other.plate_number);
  await expect(row.locator('[data-requested]')).toContainText('متاحة');
  await row.getByRole('button', { name: 'رفض' }).click();
  await top().locator('[name=reason]').fill('يُصلح المكيف غداً');
  await top().getByRole('button', { name: 'رفض' }).click();
  await expect(row).toBeHidden();
  let mine = await app.call('GET', '/driver/vehicle');
  expect([mine.change_request.status, mine.change_request.note]).toEqual(['rejected', 'يُصلح المكيف غداً']);

  await app.call('POST', '/driver/vehicle-change-requests', { requested_plate: other.plate_number, reason: 'ما زال معطلاً' });
  row = await custodyPage();
  await row.getByRole('button', { name: 'تم التغيير' }).click();
  await top().getByRole('button', { name: 'تم التغيير' }).click();
  await expect(row).toBeHidden();
  mine = await app.call('GET', '/driver/vehicle');
  expect([mine.change_request.status, mine.change_request.requested_plate]).toEqual(['done', other.plate_number]);

  // ---- the history keeps both, closed, with the car asked for; filtered by status, and exported
  const history = admin.locator('[data-change-history]');
  const mineRows = history.locator('tbody tr', { hasText: driver.name.ar });
  await expect(mineRows).toHaveCount(2);
  await expect(mineRows.first()).toContainText(other.plate_number);
  await expect(mineRows.first()).toContainText('تم التغيير');
  await expect(mineRows.last()).toContainText('مرفوض');
  await expect(mineRows.last()).toContainText('يُصلح المكيف غداً');
  await history.locator('[data-chip=rejected]').click();
  await expect(mineRows).toHaveCount(1);
  await expect(mineRows).toContainText('المكيف لا يعمل');
  await history.locator('[data-chip=""]').click();
  await expect(mineRows).toHaveCount(2);
  const [file] = await Promise.all([admin.waitForEvent('download'), history.locator('[data-change-export]').click()]);
  const sheet = readXlsx(fs.readFileSync(await file.path()));
  expect(sheet[0].slice(0, 4)).toEqual(['التاريخ', 'السائق', 'السيارة التي معه', 'السيارة المطلوبة']);
  const exported = sheet.filter((r) => r[1] === driver.name.ar);
  expect(exported.map((r) => [r[2], r[3], r[6]])).toEqual([
    [vehicle.plate_number, other.plate_number, 'تم التغيير'],
    [vehicle.plate_number, other.plate_number, 'مرفوض'],
  ]);

  // ---- and on the vehicle's page
  await admin.goto('/admin.html#/vehicles/' + other.id);
  await settled(admin);
  await expect(admin.locator('[data-change-history] tbody tr', { hasText: driver.name.ar })).toHaveCount(2);

  // ---- a renewed residence: checked against its photo, approved, now his current one
  const expiry = (days) => new Date(Date.now() + days * 86400e3).toISOString().slice(0, 10);
  await api.post('/documents', {
    owner_type: 'employee', owner_id: driver.id, type_code: 'residence', number: 'RES-' + n, expiry_date: expiry(12),
    file_sha256: await api.upload('res.jpg', 'image/jpeg', jpeg()),
  });
  await app.call('POST', '/driver/documents/renewals', { type_code: 'residence', number: 'RES2-' + n, expiry_date: expiry(400), file_sha256: await app.photo() });
  await admin.goto('/admin.html#/employees?tab=docs');
  await admin.reload();
  await settled(admin);
  row = admin.locator('[data-pending=renewals] [data-pending-id]', { hasText: driver.name.ar });
  await expect(row).toContainText('RES2-' + n);
  await expect(row.locator('img')).toHaveCount(1);
  await row.getByRole('button', { name: 'اعتماد' }).click();
  await top().getByRole('button', { name: 'اعتماد' }).click();
  await expect(row).toBeHidden();
  const docs = await api.get(`/documents?owner_type=employee&owner_id=${driver.id}`);
  expect(docs.filter((d) => d.type_code === 'residence').map((d) => [d.number, d.expiry_date])).toEqual([['RES2-' + n, expiry(400)]]);
  const told = (await app.call('GET', '/driver/notifications')).items.map((x) => x.kind);
  expect(told.slice(0, 3)).toEqual(['document_renewal_approved', 'vehicle_change_done', 'vehicle_change_rejected']);
});
