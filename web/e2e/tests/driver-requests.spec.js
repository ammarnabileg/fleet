// What drivers ask for from the app and the office decides (BRD FR-ASG-04, FR-APP-05): a change of vehicle refused
// with its reason then closed as done, from the custody page; a renewed residence checked against its photo and
// approved, from the documents tab, after which it is the driver's current one.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

test('a change of vehicle refused then done, and a renewed document approved', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الطلبات ' + n, en: 'Requests company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '7/' + n.slice(-6), make: 'Kia', model: 'Rio', company_id: company.id, last_odometer_km: 5000 });
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

  // ---- a change of vehicle: refused with the reason, asked again, then closed as done
  await app.call('POST', '/driver/vehicle-change-requests', { reason: 'المكيف لا يعمل' });
  const custodyPage = async () => {
    await admin.goto('/admin.html#/custody');
    await admin.reload();
    await settled(admin);
    return admin.locator('[data-pending=vehicle-changes] [data-pending-id]', { hasText: driver.name.ar });
  };
  let row = await custodyPage();
  await expect(row).toContainText('المكيف لا يعمل');
  await expect(row).toContainText(vehicle.plate_number);
  await row.getByRole('button', { name: 'رفض' }).click();
  await top().locator('[name=reason]').fill('يُصلح المكيف غداً');
  await top().getByRole('button', { name: 'رفض' }).click();
  await expect(row).toBeHidden();
  let mine = await app.call('GET', '/driver/vehicle');
  expect([mine.change_request.status, mine.change_request.note]).toEqual(['rejected', 'يُصلح المكيف غداً']);

  await app.call('POST', '/driver/vehicle-change-requests', { reason: 'ما زال معطلاً' });
  row = await custodyPage();
  await row.getByRole('button', { name: 'تم التغيير' }).click();
  await top().getByRole('button', { name: 'تم التغيير' }).click();
  await expect(row).toBeHidden();
  mine = await app.call('GET', '/driver/vehicle');
  expect(mine.change_request.status).toBe('done');

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
